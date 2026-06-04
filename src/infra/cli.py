"""
Entrypoint de línea de comandos (CLI) para ejecutar los workers de monitoreo.
Permite ejecutar el scraping basado en un archivo YAML específico o correr todas las fuentes activas.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application.use_cases import MonitoreoUseCase
from src.core.domain.entities import Fuente
from src.core.domain.exceptions import GrantPulseError
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
from src.infra.scraping.funding_pipeline import build_scraper_for_source, source_profile_for_name

logger = get_logger(__name__)


def _apply_source_profile(fuente: Fuente) -> Fuente:
    """Normaliza una fuente usando el registry duro si existe."""

    source_profile = source_profile_for_name(fuente.nombre)
    if not source_profile:
        return fuente

    nueva_config = fuente.configuracion_reglas.model_copy(update={"url_busqueda": source_profile.list_url})
    return fuente.model_copy(update={"url_base": source_profile.root_url, "configuracion_reglas": nueva_config})


def _get_scraper(fuente: Fuente) -> ScraperPort:
    """Retorna la implementación del scraper según la estrategia definida."""
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


async def run_single_source(filepath: Path) -> None:
    """Ejecuta el ciclo de monitoreo para una fuente específica desde un YAML."""
    logger.info("Iniciando worker para fuente específica", filepath=str(filepath))

    rules_config = load_rules_from_yaml(filepath)
    source_profile = source_profile_for_name(rules_config.nombre)
    if source_profile:
        rules_config = rules_config.model_copy(update={"url_busqueda": source_profile.list_url})
        logger.info(
            "Aplicando URL canónica desde registry duro",
            fuente=rules_config.nombre,
            url_busqueda=str(rules_config.url_busqueda),
            profile=source_profile.key,
        )

    async with AsyncSessionLocal() as session:
        try:
            fuente_repo = SQLFuenteRepository(session)
            snapshot_repo = SQLSnapshotRepository(session)
            convocatoria_repo = SQLConvocatoriaRepository(session)

            fuente_db = await fuente_repo.get_by_nombre(rules_config.nombre)

            if not fuente_db:
                fuente_db = Fuente(
                    id=uuid4(),
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
                scraper=scraper, snapshot_repo=snapshot_repo, convocatoria_repo=convocatoria_repo, notifier=notifier,
                notificacion_repo=notificacion_repo,
            )

            eventos = await use_case.ejecutar_monitoreo(fuente_db)
            await session.commit()
            logger.info(f"Proceso finalizado. Eventos generados: {len(eventos)}")
        except Exception as e:
            await session.rollback()
            logger.error("Error en monitoreo de fuente, session rollback ejecutado", exc=e)
            raise


async def run_all_active_sources() -> None:
    """Ejecuta el ciclo de monitoreo para todas las fuentes activas en la BD."""
    logger.info("Iniciando worker para todas las fuentes activas")

    fuentes_activas: list[Fuente] = []
    async with AsyncSessionLocal() as session:
        try:
            fuente_repo = SQLFuenteRepository(session)
            fuentes_activas = await fuente_repo.get_all_active()
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Error consultando fuentes activas al iniciar: {e}", exc=e)
            raise

    if not fuentes_activas:
        logger.warning("No hay fuentes activas configuradas en la base de datos.")
        return

    failed_fuentes: list[str] = []

    for fuente in fuentes_activas:
        async with AsyncSessionLocal() as session:
            try:
                snapshot_repo = SQLSnapshotRepository(session)
                convocatoria_repo = SQLConvocatoriaRepository(session)
                notificacion_repo = SQLNotificacionRepository(session)
                fuente = _apply_source_profile(fuente)
                scraper = _get_scraper(fuente)
                notifier = await _get_notifier(session)

                use_case = MonitoreoUseCase(
                    scraper=scraper, snapshot_repo=snapshot_repo, convocatoria_repo=convocatoria_repo, notifier=notifier,
                    notificacion_repo=notificacion_repo,
                )

                await use_case.ejecutar_monitoreo(fuente)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Worker falló para fuente {fuente.nombre}: {e}", exc=e)
                failed_fuentes.append(fuente.nombre)

    if failed_fuentes:
        logger.error("Fuentes con error en batch", count=len(failed_fuentes), fuentes=failed_fuentes)
    else:
        logger.info("Batch completado sin errores", total_fuentes=len(fuentes_activas))


async def sync_all_rules() -> None:
    """Escanea el directorio de reglas y sincroniza todas las fuentes."""
    from src.infra.config import settings

    rules_path = Path(settings.RULES_DIR)
    if not rules_path.exists():
        logger.error(f"Directorio de reglas no encontrado: {rules_path}")
        return

    failed_files: list[str] = []

    for yaml_file in rules_path.glob("*.yaml"):
        logger.info(f"Sincronizando regla: {yaml_file.name}")
        try:
            await run_single_source(yaml_file)
        except Exception as e:
            logger.error(f"Error procesando {yaml_file.name}", exc=e)
            failed_files.append(yaml_file.name)

    if failed_files:
        logger.error("Archivos con error en sync-rules", count=len(failed_files), archivos=failed_files)
    else:
        logger.info("sync-rules completado sin errores")


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
    except GrantPulseError as e:
        logger.error("Error de dominio finalizando el worker", exc=e)
        sys.exit(1)
    except Exception as e:
        logger.error("Error no manejado finalizando el worker", exc=e)
        sys.exit(1)


if __name__ == "__main__":
    main()
