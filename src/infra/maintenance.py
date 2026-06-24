"""Módulo para tareas de mantenimiento en la base de datos."""

import asyncio
from datetime import UTC, datetime, timedelta

from pydantic import HttpUrl
from sqlalchemy import delete, select

from src.core.application.normalizer import _infer_region_with_llm
from src.core.application.run_context import clear_run_id, new_run_id
from src.core.domain.entities import Fuente, RulesConfig
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM, FuenteORM, HistorialCambiosORM
from src.infra.logging import get_logger

logger = get_logger(__name__)

_ESTADOS_NO_VIGENTES = frozenset({"CERRADO", "ADJUDICADO", "SUSPENDIDO", "FINALIZADO"})


async def clean_expired_convocatorias(dias_vencida: int = 7) -> int:
    """
    Elimina convocatorias cuya fecha de cierre haya pasado hace `dias_vencida` o más
    y cuyo estado sea no vigente (CERRADO, ADJUDICADO, SUSPENDIDO, FINALIZADO).

    Regla de negocio: una convocatoria vencida > N días sin posibilidad de reactivación
    se purga para mantener la BD liviana y los datos relevantes.
    """
    run_id = new_run_id()
    limite = datetime.now(UTC) - timedelta(days=dias_vencida)
    logger.info(
        "Iniciando purga de convocatorias vencidas", run_id=run_id, dias_vencida=dias_vencida, limite=str(limite.date())
    )

    async with AsyncSessionLocal() as session:
        try:
            # Obtener IDs de convocatorias a eliminar
            query = select(ConvocatoriaORM.id).where(
                ConvocatoriaORM.fecha_cierre.is_not(None),
                ConvocatoriaORM.fecha_cierre < limite,
                ConvocatoriaORM.estado.in_(_ESTADOS_NO_VIGENTES),
            )
            result = await session.execute(query)
            ids_to_delete = list(result.scalars().all())

            if not ids_to_delete:
                logger.info("No hay convocatorias vencidas para purgar", run_id=run_id)
                return 0

            # Eliminar historial primero (FK)
            await session.execute(
                delete(HistorialCambiosORM).where(HistorialCambiosORM.convocatoria_id.in_(ids_to_delete))
            )
            # Eliminar convocatorias
            await session.execute(delete(ConvocatoriaORM).where(ConvocatoriaORM.id.in_(ids_to_delete)))

            await session.commit()
            logger.info("Purga completada", eliminadas=len(ids_to_delete), run_id=run_id)
            return len(ids_to_delete)
        except Exception as e:
            await session.rollback()
            logger.error("Error en purga de convocatorias vencidas", exc=e, run_id=run_id)
            raise
        finally:
            clear_run_id()


async def run_backfill_regions(limit: int | None = None) -> int:
    """Completa regiones faltantes en convocatorias existentes usando inferencia LLM cuando sea posible."""

    run_id = new_run_id()
    logger.info("Iniciando backfill de regiones", run_id=run_id, limit=limit)

    async with AsyncSessionLocal() as session:
        try:
            from sqlalchemy import String

            query = select(ConvocatoriaORM).where(ConvocatoriaORM.regiones.cast(String) == "[]")
            if limit is not None:
                query = query.limit(limit)

            result = await session.execute(query)
            convocatorias = result.scalars().all()

            updated = 0
            for convocatoria in convocatorias:
                fuente_orm = await session.get(FuenteORM, convocatoria.fuente_id)
                if not fuente_orm:
                    continue

                try:
                    rules_config = RulesConfig.model_validate_json(fuente_orm.configuracion_yaml)
                    fuente = Fuente(
                        id=fuente_orm.id,
                        nombre=fuente_orm.nombre,
                        url_base=HttpUrl(fuente_orm.url_base),
                        configuracion_reglas=rules_config,
                        activa=fuente_orm.activa,
                        creado_en=fuente_orm.creado_en,
                        actualizado_en=fuente_orm.actualizado_en,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "No se pudo reconstruir la fuente para backfill de región",
                        convocatoria_id=str(convocatoria.id),
                        fuente_id=str(fuente_orm.id),
                        exc=exc,
                    )
                    continue

                # Primero intentar inferencia determinística (sin LLM)
                from src.core.application.region_inferrer import inferir_regiones as _inferir_heuristica

                regiones = _inferir_heuristica(
                    convocatoria.titulo, convocatoria.descripcion or ""
                )

                # Fallback a LLM solo si la heurística no encontró nada
                if not regiones:
                    regiones = _infer_region_with_llm(
                        convocatoria.titulo, convocatoria.descripcion, convocatoria.url_detail, fuente
                    )

                if regiones:
                    convocatoria.regiones = regiones
                    updated += 1

            await session.commit()
            logger.info("Backfill de regiones finalizado", run_id=run_id, actualizados=updated)
            return updated
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            logger.error("Error en backfill de regiones", run_id=run_id, exc=exc)
            raise
        finally:
            clear_run_id()


async def clean_unavailable_convocatorias(dias_gracia: int = 30) -> int:
    """
    Elimina convocatorias que fueron marcadas como no disponibles (url_check_failed=True)
    y cuyo último check fallido fue hace más de `dias_gracia`.
    """
    run_id = new_run_id()
    limite = datetime.now(UTC) - timedelta(days=dias_gracia)
    logger.info(
        "Iniciando purga de convocatorias no disponibles", run_id=run_id, dias_gracia=dias_gracia, limite=str(limite.date())
    )

    async with AsyncSessionLocal() as session:
        try:
            from sqlalchemy import String, cast

            query = select(ConvocatoriaORM.id).where(
                ConvocatoriaORM.ultimo_check_url.is_not(None),
                ConvocatoriaORM.ultimo_check_url < limite,
                cast(ConvocatoriaORM.metadatos["url_check_failed"], String) == "true"
            )
            result = await session.execute(query)
            ids_to_delete = list(result.scalars().all())

            if not ids_to_delete:
                logger.info("No hay convocatorias no disponibles para purgar", run_id=run_id)
                return 0

            await session.execute(
                delete(HistorialCambiosORM).where(HistorialCambiosORM.convocatoria_id.in_(ids_to_delete))
            )
            await session.execute(delete(ConvocatoriaORM).where(ConvocatoriaORM.id.in_(ids_to_delete)))

            await session.commit()
            logger.info("Purga de no disponibles completada", eliminadas=len(ids_to_delete), run_id=run_id)
            return len(ids_to_delete)
        except Exception as e:
            await session.rollback()
            logger.error("Error en purga de convocatorias no disponibles", exc=e, run_id=run_id)
            raise
        finally:
            clear_run_id()


async def run_clean_db() -> None:
    """Borra registros con más de 6 meses de creados y que no estén activos/vigentes."""
    run_id = new_run_id()
    logger.info("Iniciando tarea de limpieza de base de datos (registros inactivos > 6 meses)", run_id=run_id)
    seis_meses_atras = datetime.now(UTC) - timedelta(days=180)

    async with AsyncSessionLocal() as session:
        try:
            query = select(ConvocatoriaORM.id).where(
                ConvocatoriaORM.creado_en < seis_meses_atras,
                ConvocatoriaORM.estado != "ABIERTO",
            )
            result = await session.execute(query)
            ids_to_delete = result.scalars().all()

            if not ids_to_delete:
                logger.info("No hay registros antiguos inactivos que borrar.", run_id=run_id)
                return

            await session.execute(
                delete(HistorialCambiosORM).where(HistorialCambiosORM.convocatoria_id.in_(ids_to_delete))
            )

            await session.execute(delete(ConvocatoriaORM).where(ConvocatoriaORM.id.in_(ids_to_delete)))

            await session.commit()
            logger.info("Limpieza completada", eliminados=len(ids_to_delete), run_id=run_id)
        except Exception as e:
            await session.rollback()
            logger.error("Error limpiando base de datos", exc=e, run_id=run_id)
            raise
        finally:
            clear_run_id()

async def normalize_existing_urls() -> int:
    """Normaliza las URLs guardadas en BD y resetea su estado de error."""
    from sqlalchemy.orm.attributes import flag_modified

    from src.core.application.normalizer import _is_valid_url

    run_id = new_run_id()
    logger.info("Iniciando normalización de URLs existentes", run_id=run_id)

    async with AsyncSessionLocal() as session:
        try:
            query = select(ConvocatoriaORM, FuenteORM).join(FuenteORM, ConvocatoriaORM.fuente_id == FuenteORM.id)
            result = await session.execute(query)
            rows = result.all()

            updated_count = 0
            reset_count = 0

            for conv_orm, fuente_orm in rows:
                changed = False

                # 1. Normalizar url_detail
                if conv_orm.url_detail:
                    url_temp = conv_orm.url_detail
                    if url_temp.startswith("/") or not url_temp.startswith("http"):
                        if url_temp.startswith("/"):
                            url_temp = str(fuente_orm.url_base).rstrip("/") + "/" + url_temp.lstrip("/")
                        else:
                            url_temp = str(fuente_orm.url_base).rstrip("/") + "/" + url_temp

                    if _is_valid_url(url_temp) and url_temp != conv_orm.url_detail:
                        logger.info("Normalizando URL", identificador=conv_orm.identificador_externo, original=conv_orm.url_detail, nueva=url_temp)
                        conv_orm.url_detail = url_temp
                        changed = True

                # 2. Reiniciar el estado de url_check_failed
                metadatos = dict(conv_orm.metadatos or {})
                if "url_check_failed" in metadatos:
                    logger.info("Reiniciando flag de fallo de URL", identificador=conv_orm.identificador_externo)
                    del metadatos["url_check_failed"]
                    conv_orm.metadatos = metadatos
                    flag_modified(conv_orm, "metadatos")
                    changed = True
                    reset_count += 1

                if changed:
                    updated_count += 1

            if updated_count > 0:
                await session.commit()
                logger.info("Normalización completada", actualizados=updated_count, resets_error_url=reset_count, run_id=run_id)
            else:
                logger.info("No se requirió ninguna normalización en base de datos", run_id=run_id)
            return updated_count
        except Exception as e:
            await session.rollback()
            logger.error("Error en normalización de URLs", exc=e, run_id=run_id)
            raise
        finally:
            clear_run_id()
if __name__ == "__main__":
    asyncio.run(run_clean_db())
