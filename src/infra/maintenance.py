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


async def run_backfill_regions(limit: int | None = None) -> int:
    """Completa regiones faltantes en convocatorias existentes usando inferencia LLM cuando sea posible."""

    run_id = new_run_id()
    logger.info("Iniciando backfill de regiones", run_id=run_id, limit=limit)

    async with AsyncSessionLocal() as session:
        try:
            query = select(ConvocatoriaORM).where(ConvocatoriaORM.region.is_(None))
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

                region = _infer_region_with_llm(convocatoria.titulo, convocatoria.descripcion, convocatoria.url_detail, fuente)
                if region:
                    convocatoria.region = region
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

            await session.execute(delete(HistorialCambiosORM).where(HistorialCambiosORM.convocatoria_id.in_(ids_to_delete)))

            await session.execute(delete(ConvocatoriaORM).where(ConvocatoriaORM.id.in_(ids_to_delete)))

            await session.commit()
            logger.info("Limpieza completada", eliminados=len(ids_to_delete), run_id=run_id)
        except Exception as e:
            await session.rollback()
            logger.error("Error limpiando base de datos", exc=e, run_id=run_id)
            raise
        finally:
            clear_run_id()


if __name__ == "__main__":
    asyncio.run(run_clean_db())
