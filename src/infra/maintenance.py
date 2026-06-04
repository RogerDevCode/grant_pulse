"""
Módulo para tareas de mantenimiento en la base de datos.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM, HistorialCambiosORM
from src.infra.logging import get_logger

logger = get_logger(__name__)


async def run_clean_db() -> None:
    """Borra registros con más de 6 meses de creados y que no estén activos/vigentes."""
    logger.info("Iniciando tarea de limpieza de base de datos (registros inactivos > 6 meses)")
    seis_meses_atras = datetime.now(UTC) - timedelta(days=180)

    async with AsyncSessionLocal() as session:
        try:
            # Seleccionar los IDs de las convocatorias a borrar
            query = select(ConvocatoriaORM.id).where(
                ConvocatoriaORM.creado_en < seis_meses_atras,
                ConvocatoriaORM.estado != "ABIERTO",
            )
            result = await session.execute(query)
            ids_to_delete = result.scalars().all()

            if not ids_to_delete:
                logger.info("No hay registros antiguos inactivos que borrar.")
                return

            # Delete related HistorialCambiosORM to avoid FK constraint errors if no cascade
            await session.execute(delete(HistorialCambiosORM).where(HistorialCambiosORM.convocatoria_id.in_(ids_to_delete)))
            
            # Now delete the old convocatorias
            await session.execute(delete(ConvocatoriaORM).where(ConvocatoriaORM.id.in_(ids_to_delete)))
            
            await session.commit()
            logger.info(f"Limpieza completada. Se eliminaron {len(ids_to_delete)} convocatorias antiguas y sus historiales.")
        except Exception as e:
            await session.rollback()
            logger.error("Error limpiando base de datos", exc=e)
            raise


if __name__ == "__main__":
    asyncio.run(run_clean_db())
