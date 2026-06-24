"""
Entrypoint de línea de comandos (CLI) para ejecutar los workers de monitoreo.
Permite ejecutar el scraping basado en un archivo YAML específico o correr todas las fuentes activas.
"""
# ruff: noqa: E402

import argparse
import asyncio
import os
import sys

# Desactivar variables de entorno de proxy que rompen curl_cffi en Railway
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

# Asegurar que el directorio de datos existe
os.makedirs("data", exist_ok=True)

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application.run_context import clear_run_id, new_run_id
from src.core.application.use_cases import MonitoreoUseCase
from src.core.domain.entities import Fuente
from src.core.domain.exceptions import ConfigurationError, GrantPulseError, ScrapingError
from src.core.domain.ports import (
    NotificationPort,
    ScraperPort,
)
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.repository import (
    SQLConvocatoriaRepository,
    SQLFuenteRepository,
    SQLNotificacionRepository,
    SQLSnapshotRepository,
)
from src.infra.logging import get_logger
from src.infra.notifications.composite_adapter import CompositeNotificationAdapter
from src.infra.notifications.email_adapter import EmailNotificationAdapter
from src.infra.notifications.logger_adapter import LoggerNotificationAdapter
from src.infra.notifications.telegram_adapter import TelegramNotificationAdapter
from src.infra.rules_loader import load_rules_from_yaml

logger = get_logger(__name__)


def _apply_source_profile(fuente: Fuente) -> Fuente:
    """Normaliza una fuente usando el registry duro si existe."""
    from pydantic import HttpUrl, TypeAdapter

    from src.infra.sources.catalog import source_profile_for_name

    source_profile = source_profile_for_name(fuente.nombre)
    if not source_profile:
        return fuente

    list_url_obj = TypeAdapter(HttpUrl).validate_python(source_profile.list_url)
    root_url_obj = TypeAdapter(HttpUrl).validate_python(source_profile.root_url)

    nueva_config = fuente.configuracion_reglas.model_copy(update={"url_busqueda": list_url_obj})
    return fuente.model_copy(update={"url_base": root_url_obj, "configuracion_reglas": nueva_config})


def _get_scraper(fuente: Fuente) -> ScraperPort:
    """Retorna la implementación del scraper según la estrategia definida."""
    from src.infra.scraping.funding_pipeline import build_scraper_for_source

    return build_scraper_for_source(fuente)


async def _get_notifier(session: AsyncSession) -> NotificationPort:
    """Configura el notificador con los adaptadores disponibles, incluyendo los de la BD."""
    from sqlalchemy import select

    from src.infra.config import settings
    from src.infra.db.models import NotificacionConfigORM

    adapters: list[NotificationPort] = [LoggerNotificationAdapter()]

    # 1. Adaptador desde .env (Legacy/Global)
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        adapters.append(TelegramNotificationAdapter())

    # 2. Adaptadores dinámicos desde la BD
    try:
        result = await session.execute(select(NotificacionConfigORM).where(NotificacionConfigORM.activa))
        configs = result.scalars().all()
        for config in configs:
            if config.tipo == "TELEGRAM":
                # Creamos un adaptador específico para este token/chat_id
                token = str(config.configuracion.get("token", ""))
                chat_id = str(config.configuracion.get("chat_id", ""))
                adapter = TelegramNotificationAdapter(bot_token=token, chat_id=chat_id)
                adapters.append(adapter)
            elif config.tipo == "EMAIL":
                c = config.configuracion
                email_adapter = EmailNotificationAdapter(
                    host=str(c.get("host", "")),
                    port=int(c.get("port", 587)),
                    user=str(c.get("user", "")),
                    password=str(c.get("password", "")),
                    from_email=str(c.get("from_email", "")),
                    target_emails=list(c.get("target_emails", [])),
                    use_tls=bool(c.get("use_tls", True)),
                )
                adapters.append(email_adapter)
    except Exception as e:
        logger.error("Error cargando notificaciones dinámicas desde BD, se usarán solo adaptadores estáticos", exc=e)

    return CompositeNotificationAdapter(adapters)


async def _notify_subscribers(
    session: AsyncSession,
    eventos: list[Any],
    nuevas_dict: dict[Any, Any],
    fuente: Fuente,
) -> None:
    """Notifica a suscriptores por región sobre nuevas aperturas."""
    from sqlalchemy import select

    from src.infra.db.models import SuscripcionORM

    if not eventos:
        return

    try:
        result = await session.execute(
            select(SuscripcionORM).where(SuscripcionORM.activa.is_(True), SuscripcionORM.confirmado.is_(True))
        )
        suscripciones = result.scalars().all()
    except Exception as e:
        logger.warning("Error cargando suscripciones para notificación", exc=e)
        return

    if not suscripciones:
        return

    from src.infra.config import settings

    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado; no se enviarán notificaciones a suscriptores")
        return

    for evento in eventos:
        if not evento.es_relevante:
            continue
        conv = nuevas_dict.get(evento.convocatoria_id)
        if not conv:
            continue

        regiones_conv = [r.strip().lower() for r in (conv.regiones or [])]
        if not regiones_conv:
            regiones_conv = ["nacional"]

        for sub in suscripciones:
            regiones_sub = [r.strip().lower() for r in (sub.regiones or [])]
            match = False
            if not regiones_sub or "todas" in regiones_sub or "nacional" in regiones_sub:
                match = True
            else:
                for rc in regiones_conv:
                    if rc in regiones_sub or rc == "nacional":
                        match = True
                        break

            if not match:
                continue

            # Enviar mensaje
            regiones_str = ", ".join(conv.regiones) if conv.regiones else "Nacional"
            mensaje = (
                f"<b>🆕 Nueva Convocatoria</b>\n"
                f"🏛 <i>{fuente.nombre}</i>\n\n"
                f"<b>{conv.titulo}</b>\n"
                f"📍 <b>Región:</b> {regiones_str}\n"
            )
            if conv.monto:
                mensaje += f"💰 <b>Monto:</b> ${conv.monto:,.0f}\n"
            if conv.fecha_cierre:
                mensaje += f"📅 <b>Cierre:</b> {conv.fecha_cierre.strftime('%d/%m/%Y')}\n"
            if conv.url_detalle:
                mensaje += f"\n🔗 <a href='{conv.url_detalle}'>Ver detalle</a>"

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": sub.chat_id,
                            "text": mensaje,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": False,
                        },
                    )
                    resp.raise_for_status()
                logger.info("Notificación enviada a suscriptor", chat_id=sub.chat_id, convocatoria=conv.titulo[:60])
            except Exception as e:
                logger.warning("Error enviando notificación a suscriptor", chat_id=sub.chat_id, error=str(e))


async def run_single_source(filepath: Path) -> None:
    """Ejecuta el ciclo de monitoreo para una fuente específica desde un YAML."""
    run_id = new_run_id()
    logger.info("Iniciando worker para fuente específica", filepath=str(filepath), run_id=run_id)

    try:
        rules_config = load_rules_from_yaml(filepath)
        from src.infra.sources.catalog import source_profile_for_name

        source_profile = source_profile_for_name(rules_config.nombre)
        if source_profile:
            from pydantic import HttpUrl, TypeAdapter

            list_url_obj = TypeAdapter(HttpUrl).validate_python(source_profile.list_url)
            rules_config = rules_config.model_copy(update={"url_busqueda": list_url_obj})
            logger.info(
                "Aplicando URL canónica desde registry duro",
                fuente=rules_config.nombre,
                url_busqueda=str(rules_config.url_busqueda),
                profile=source_profile.key,
            )

        async with AsyncSessionLocal() as session:
            fuente_repo = SQLFuenteRepository(session)
            snapshot_repo = SQLSnapshotRepository(session)
            convocatoria_repo = SQLConvocatoriaRepository(session)

            fuente_db = await fuente_repo.get_by_nombre(rules_config.nombre)

            if not fuente_db:
                fuente_db = Fuente(
                    nombre=rules_config.nombre,
                    url_base=cast(Any, source_profile.root_url if source_profile else rules_config.url_busqueda),
                    configuracion_reglas=rules_config,
                    activa=True,
                )
            else:
                fuente_db.configuracion_reglas = rules_config
                fuente_db.url_base = cast(Any, source_profile.root_url if source_profile else rules_config.url_busqueda)

            fuente_db = _apply_source_profile(fuente_db)
            fuente_db = await fuente_repo.save(fuente_db)

            scraper = _get_scraper(fuente_db)
            notifier = await _get_notifier(session)
            notificacion_repo = SQLNotificacionRepository(session)

            use_case = MonitoreoUseCase(
                scraper=scraper,
                snapshot_repo=snapshot_repo,
                convocatoria_repo=convocatoria_repo,
                notifier=notifier,
                notificacion_repo=notificacion_repo,
            )

            eventos, nuevas_convocatorias = await use_case.ejecutar_monitoreo(fuente_db)
            await session.commit()

            # Notificar a suscriptores por región
            nuevas_dict = {c.id: c for c in nuevas_convocatorias}
            await _notify_subscribers(session, eventos, nuevas_dict, fuente_db)

            logger.info(f"Proceso finalizado. Eventos generados: {len(eventos)}")
    except Exception as e:
        logger.error("Error en monitoreo de fuente", filepath=str(filepath), exc=e, run_id=run_id)
        raise
    finally:
        clear_run_id()

    # Purga automática de convocatorias vencidas después de cada ciclo
    try:
        from src.infra.maintenance import clean_expired_convocatorias, clean_unavailable_convocatorias  # noqa: PLC0415

        purgadas = await clean_expired_convocatorias(dias_vencida=7)
        if purgadas > 0:
            logger.info("Limpieza automática de vencidas completada", eliminadas=purgadas)

        purgadas_unav = await clean_unavailable_convocatorias(dias_gracia=30)
        if purgadas_unav > 0:
            logger.info("Limpieza automática de no disponibles completada", eliminadas=purgadas_unav)
    except Exception as e:
        logger.warning("Limpieza automática falló (no crítica)", exc=e)


async def run_all_active_sources() -> None:
    """Ejecuta el ciclo de monitoreo para todas las fuentes activas en la BD."""
    run_id = new_run_id()
    logger.info("Iniciando worker para todas las fuentes activas", run_id=run_id)

    try:
        fuentes_activas: list[Fuente] = []
        async with AsyncSessionLocal() as session:
            fuente_repo = SQLFuenteRepository(session)
            fuentes_activas = await fuente_repo.get_all_active()
            await session.commit()
        if not fuentes_activas:
            logger.warning("No hay fuentes activas configuradas en la base de datos.")
            return

        failed_fuentes: list[str] = []

        # Fase 1: Limitar la concurrencia a maximo 3 tareas simultaneas en el event loop
        sem = asyncio.Semaphore(3)

        async def procesar_fuente(fuente_inst: Fuente) -> None:
            async with sem:
                fuente_run_id = new_run_id()
                async with AsyncSessionLocal() as session:
                    try:
                        snapshot_repo = SQLSnapshotRepository(session)
                        convocatoria_repo = SQLConvocatoriaRepository(session)
                        notificacion_repo = SQLNotificacionRepository(session)
                        fuente_normalizada = _apply_source_profile(fuente_inst)
                        scraper = _get_scraper(fuente_normalizada)
                        notifier = await _get_notifier(session)

                        use_case = MonitoreoUseCase(
                            scraper=scraper,
                            snapshot_repo=snapshot_repo,
                            convocatoria_repo=convocatoria_repo,
                            notifier=notifier,
                            notificacion_repo=notificacion_repo,
                        )

                        await use_case.ejecutar_monitoreo(fuente_normalizada)
                        await session.commit()
                    except Exception as e:
                        await session.rollback()
                        logger.error(
                            f"Worker falló para fuente {fuente_inst.nombre}: {e}",
                            exc=e,
                            fuente_id=str(fuente_inst.id),
                            run_id=fuente_run_id,
                        )
                        failed_fuentes.append(fuente_inst.nombre)

                        # Guardar error estructurado en base de datos para observabilidad
                        import traceback

                        from src.infra.db.models import AuditLogORM

                        try:
                            audit = AuditLogORM(
                                fuente_id=int(fuente_inst.id) if str(fuente_inst.id).isdigit() else None,
                                nivel="ERROR",
                                modulo="cli.run_all_active_sources",
                                mensaje=f"Worker falló para fuente {fuente_inst.nombre}: {e}",
                                detalles={
                                    "run_id": fuente_run_id,
                                    "error": str(e),
                                    "traceback": traceback.format_exc(),
                                },
                            )
                            session.add(audit)
                            await session.commit()
                        except Exception as inner_e:
                            logger.error("No se pudo guardar el audit log en base de datos", exc=inner_e)

        # Ejecutar concurrentemente todas las tareas con control de concurrencia
        tareas = [procesar_fuente(fuente) for fuente in fuentes_activas]
        await asyncio.gather(*tareas)

        # Generar reporte de calidad
        async with AsyncSessionLocal() as session:
            from src.infra.quality_report import generar_reporte_calidad

            report_path = Path("reports") / f"quality_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.md"
            try:
                await generar_reporte_calidad(session, report_path)
            except Exception as e:
                logger.error("Error generando reporte de calidad", exc=e, run_id=run_id)

        if failed_fuentes:
            msg = f"Fuentes con error en batch: {', '.join(failed_fuentes)}"
            logger.error("Fuentes con error en batch", count=len(failed_fuentes), fuentes=failed_fuentes)
            raise ScrapingError(msg)

        logger.info("Batch completado sin errores", total_fuentes=len(fuentes_activas))
    finally:
        clear_run_id()

    # Purga automática de convocatorias vencidas/no disponibles
    try:
        from src.infra.maintenance import clean_expired_convocatorias, clean_unavailable_convocatorias

        purgadas = await clean_expired_convocatorias(dias_vencida=7)
        if purgadas > 0:
            logger.info("Limpieza automática de vencidas completada", eliminadas=purgadas)

        purgadas_unav = await clean_unavailable_convocatorias(dias_gracia=30)
        if purgadas_unav > 0:
            logger.info("Limpieza automática de no disponibles completada", eliminadas=purgadas_unav)
    except Exception as e:
        logger.warning("Limpieza automática falló (no crítica)", exc=e)


async def sync_single_source_config(filepath: Path) -> None:
    """Carga un archivo YAML de reglas y lo sincroniza con la base de datos sin ejecutar el monitoreo."""
    rules_config = load_rules_from_yaml(filepath)
    from src.infra.sources.catalog import source_profile_for_name

    source_profile = source_profile_for_name(rules_config.nombre)
    if source_profile:
        from pydantic import HttpUrl, TypeAdapter

        list_url_obj = TypeAdapter(HttpUrl).validate_python(source_profile.list_url)
        rules_config = rules_config.model_copy(update={"url_busqueda": list_url_obj})
        logger.info(
            "Aplicando URL canónica desde registry duro",
            fuente=rules_config.nombre,
            url_busqueda=str(rules_config.url_busqueda),
            profile=source_profile.key,
        )

    async with AsyncSessionLocal() as session:
        try:
            fuente_repo = SQLFuenteRepository(session)
            fuente_db = await fuente_repo.get_by_nombre(rules_config.nombre)

            if not fuente_db:
                fuente_db = Fuente(
                    nombre=rules_config.nombre,
                    url_base=cast(Any, source_profile.root_url if source_profile else rules_config.url_busqueda),
                    configuracion_reglas=rules_config,
                    activa=rules_config.activa,
                )
            else:
                fuente_db.configuracion_reglas = rules_config
                fuente_db.url_base = cast(Any, source_profile.root_url if source_profile else rules_config.url_busqueda)
                fuente_db.activa = rules_config.activa

            fuente_db = _apply_source_profile(fuente_db)
            logger.debug("Fuente normalizada antes de persistir", fuente=rules_config.nombre, fuente_id=str(fuente_db.id))
            await fuente_repo.save(fuente_db)
            await session.commit()
            logger.info("Configuración de fuente sincronizada exitosamente", fuente=rules_config.nombre)
        except Exception as e:
            await session.rollback()
            logger.error("Error sincronizando configuración de fuente", fuente=rules_config.nombre, exc=e)
            raise


async def sync_all_rules() -> None:
    """Escanea el directorio de reglas y sincroniza todas las fuentes."""
    from src.infra.config import settings

    run_id = new_run_id()
    try:
        rules_path = Path(settings.RULES_DIR)
        if not rules_path.exists():
            msg = f"Directorio de reglas no encontrado: {rules_path}"
            logger.error(msg, run_id=run_id)
            raise ConfigurationError(msg)

        failed_files: list[str] = []

        for yaml_file in rules_path.glob("*.yaml"):
            logger.info(f"Sincronizando regla: {yaml_file.name}")
            try:
                await sync_single_source_config(yaml_file)
            except Exception as e:
                logger.error(f"Error procesando {yaml_file.name}", exc=e)
                failed_files.append(yaml_file.name)

        if failed_files:
            msg = f"Archivos con error en sync-rules: {', '.join(failed_files)}"
            logger.error("Archivos con error en sync-rules", count=len(failed_files), archivos=failed_files)
            raise ConfigurationError(msg)

        logger.info("sync-rules completado sin errores")
    finally:
        clear_run_id()


def main() -> None:
    parser = argparse.ArgumentParser(description="GrantPulse Worker CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Comando para correr una regla YAML específica
    run_file_parser = subparsers.add_parser("run-file", help="Ejecuta el monitoreo de un archivo YAML")
    run_file_parser.add_argument("filepath", type=Path, help="Ruta al archivo YAML de reglas")

    # Comando para correr todas las activas en BD
    subparsers.add_parser("run-all", help="Ejecuta el monitoreo de todas las fuentes activas en BD")

    # Comando para sincronizar y correr todo el directorio de reglas
    subparsers.add_parser("sync-rules", help="Escanea el directorio de reglas y ejecuta todas las fuentes encontradas")

    # Comando para limpiar la BD
    subparsers.add_parser("clean-db", help="Elimina convocatorias antiguas e inactivas (>6 meses)")

    # Comando para purgar convocatorias vencidas
    purge_parser = subparsers.add_parser(
        "purge-expired", help="Elimina convocatorias con fecha de cierre vencida > N días"
    )
    purge_parser.add_argument(
        "--dias", type=int, default=7, help="Días desde el cierre para considerar vencida (default: 7)"
    )

    purge_unav_parser = subparsers.add_parser(
        "purge-unavailable", help="Elimina convocatorias marcadas como no disponibles > N días"
    )
    purge_unav_parser.add_argument(
        "--dias", type=int, default=30, help="Días desde el fallo para considerar purga (default: 30)"
    )

    subparsers.add_parser(
        "backfill-regions", help="Completa la región en convocatorias existentes usando inferencia LLM"
    )

    enrich_parser = subparsers.add_parser(
        "enrich-details", help="Ejecuta el deep scraping para enriquecer convocatorias usando LLM"
    )
    enrich_parser.add_argument("--batch-size", type=int, default=5, help="Tamaño del lote a procesar (default: 5)")

    args = parser.parse_args()

    try:
        if args.command == "run-file":
            asyncio.run(run_single_source(args.filepath))
        elif args.command == "run-all":
            asyncio.run(run_all_active_sources())
        elif args.command == "sync-rules":
            asyncio.run(sync_all_rules())
        elif args.command == "clean-db":
            from src.infra.maintenance import run_clean_db

            asyncio.run(run_clean_db())
        elif args.command == "backfill-regions":
            from src.infra.maintenance import run_backfill_regions

            asyncio.run(run_backfill_regions())
        elif args.command == "purge-expired":
            from src.infra.maintenance import clean_expired_convocatorias

            eliminadas = asyncio.run(clean_expired_convocatorias(args.dias))
            print(f"Purga completada: {eliminadas} convocatorias vencidas eliminadas.")
        elif args.command == "purge-unavailable":
            from src.infra.maintenance import clean_unavailable_convocatorias

            eliminadas = asyncio.run(clean_unavailable_convocatorias(args.dias))
            print(f"Purga completada: {eliminadas} convocatorias no disponibles eliminadas.")
        elif args.command == "enrich-details":
            from src.infra.workers.enrichment_worker import run_enrichment_worker

            asyncio.run(run_enrichment_worker(batch_size=args.batch_size))
    except GrantPulseError as e:
        logger.error("Error de dominio finalizando el worker", exc=e)
        sys.exit(1)
    except Exception as e:
        logger.error("Error no manejado finalizando el worker", exc=e)
        sys.exit(1)


if __name__ == "__main__":
    main()
