"""Módulo para tareas de mantenimiento en la base de datos."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from src.core.application.run_context import clear_run_id, new_run_id
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM, HistorialCambiosORM
from src.infra.logging import get_logger

logger = get_logger(__name__)

_ESTADOS_NO_VIGENTES = frozenset({"CERRADO", "ADJUDICADO", "SUSPENDIDO", "FINALIZADO"})


async def clean_expired_convocatorias(dias_vencida: int = 7) -> int:
    """
    Elimina convocatorias cuya fecha de cierre haya pasado hace `dias_vencida` o más
    y cuyo estado sea no vigente (CERRADO, ADJUDICADO, SUSPENDIDO, FINALIZADO).
    """
    run_id = new_run_id()
    limite = datetime.now(UTC) - timedelta(days=dias_vencida)
    logger.info(
        "Iniciando purga de convocatorias vencidas", run_id=run_id, dias_vencida=dias_vencida, limite=str(limite.date())
    )

    async with AsyncSessionLocal() as session:
        try:
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

            await session.execute(
                delete(HistorialCambiosORM).where(HistorialCambiosORM.convocatoria_id.in_(ids_to_delete))
            )
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


async def clean_unavailable_convocatorias(dias_gracia: int = 30) -> int:
    """
    Elimina convocatorias que fueron marcadas como no disponibles (url_check_failed=True)
    y cuyo último check fallido fue hace más de `dias_gracia`.
    """
    run_id = new_run_id()
    limite = datetime.now(UTC) - timedelta(days=dias_gracia)
    logger.info(
        "Iniciando purga de convocatorias no disponibles",
        run_id=run_id,
        dias_gracia=dias_gracia,
        limite=str(limite.date()),
    )

    async with AsyncSessionLocal() as session:
        try:
            from sqlalchemy import String, cast

            query = select(ConvocatoriaORM.id).where(
                ConvocatoriaORM.ultimo_check_url.is_not(None),
                ConvocatoriaORM.ultimo_check_url < limite,
                cast(ConvocatoriaORM.metadatos["url_check_failed"], String) == "true",
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
            ids_to_delete = list(result.scalars().all())

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
