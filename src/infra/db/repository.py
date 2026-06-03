"""
Implementación de los repositorios de persistencia con SQLAlchemy 2.0 para PostgreSQL 17.
Mapea entre las entidades de dominio y los modelos ORMs.
"""

from uuid import UUID

from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.entities import Convocatoria, EventoCambio, Fuente, NotificacionResult, RulesConfig, Snapshot
from src.core.domain.exceptions import PersistenceError
from src.core.domain.ports import ConvocatoriaRepository, FuenteRepository, NotificacionRepository, SnapshotRepository
from src.infra.db.models import ConvocatoriaORM, FuenteORM, HistorialCambiosORM, NotificacionORM, SnapshotORM
from src.infra.logging import get_logger

logger = get_logger(__name__)


class SQLFuenteRepository(FuenteRepository):
    """Implementación de FuenteRepository para base de datos relacional."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: FuenteORM) -> Fuente:
        return Fuente(
            id=orm.id,
            nombre=orm.nombre,
            url_base=HttpUrl(orm.url_base),
            configuracion_reglas=RulesConfig.model_validate_json(orm.configuracion_yaml),
            activa=orm.activa,
            creado_en=orm.creado_en,
            actualizado_en=orm.actualizado_en,
        )

    async def get_by_id(self, fuente_id: UUID) -> Fuente | None:
        try:
            result = await self._session.execute(select(FuenteORM).where(FuenteORM.id == fuente_id))
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar fuente por ID: {e}"
            logger.error(msg, id=str(fuente_id), exc=e)
            raise PersistenceError(msg) from e

    async def get_by_nombre(self, nombre: str) -> Fuente | None:
        try:
            result = await self._session.execute(select(FuenteORM).where(FuenteORM.nombre == nombre))
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar fuente por nombre: {e}"
            logger.error(msg, nombre=nombre, exc=e)
            raise PersistenceError(msg) from e

    async def get_all_active(self) -> list[Fuente]:
        try:
            result = await self._session.execute(select(FuenteORM).where(FuenteORM.activa))
            orms = result.scalars().all()
            return [self._to_domain(orm) for orm in orms]
        except SQLAlchemyError as e:
            msg = f"Error al consultar fuentes activas: {e}"
            logger.error(msg, exc=e)
            raise PersistenceError(msg) from e

    async def save(self, fuente: Fuente) -> Fuente:
        try:
            result = await self._session.execute(select(FuenteORM).where(FuenteORM.id == fuente.id))
            orm = result.scalar_one_or_none()

            config_json = fuente.configuracion_reglas.model_dump_json()

            if not orm:
                orm = FuenteORM(
                    id=fuente.id,
                    nombre=fuente.nombre,
                    url_base=str(fuente.url_base),
                    configuracion_yaml=config_json,
                    activa=fuente.activa,
                    creado_en=fuente.creado_en,
                    actualizado_en=fuente.actualizado_en,
                )
                self._session.add(orm)
            else:
                orm.nombre = fuente.nombre
                orm.url_base = str(fuente.url_base)
                orm.configuracion_yaml = config_json
                orm.activa = fuente.activa
                orm.actualizado_en = fuente.actualizado_en

            await self._session.flush()
            return self._to_domain(orm)
        except SQLAlchemyError as e:
            msg = f"Error al guardar fuente {fuente.nombre}: {e}"
            logger.error(msg, source=fuente.nombre, exc=e)
            raise PersistenceError(msg) from e


class SQLSnapshotRepository(SnapshotRepository):
    """Implementación de SnapshotRepository para base de datos relacional."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: SnapshotORM) -> Snapshot:
        return Snapshot(
            id=orm.id,
            fuente_id=orm.fuente_id,
            fecha_captura=orm.fecha_captura,
            contenido_crudo=orm.contenido_crudo,
            hash_contenido=orm.hash_contenido,
            estado_ejecucion=orm.estado_ejecucion,
        )

    async def save(self, snapshot: Snapshot) -> Snapshot:
        try:
            orm = SnapshotORM(
                id=snapshot.id,
                fuente_id=snapshot.fuente_id,
                fecha_captura=snapshot.fecha_captura,
                contenido_crudo=snapshot.contenido_crudo,
                hash_contenido=snapshot.hash_contenido,
                estado_ejecucion=snapshot.estado_ejecucion,
            )
            self._session.add(orm)
            await self._session.flush()
            return self._to_domain(orm)
        except SQLAlchemyError as e:
            msg = f"Error al guardar snapshot para la fuente {snapshot.fuente_id}: {e}"
            logger.error(msg, fuente_id=str(snapshot.fuente_id), exc=e)
            raise PersistenceError(msg) from e

    async def get_latest_by_fuente(self, fuente_id: UUID) -> Snapshot | None:
        try:
            result = await self._session.execute(
                select(SnapshotORM)
                .where(SnapshotORM.fuente_id == fuente_id)
                .order_by(SnapshotORM.fecha_captura.desc())
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar último snapshot de la fuente {fuente_id}: {e}"
            logger.error(msg, fuente_id=str(fuente_id), exc=e)
            raise PersistenceError(msg) from e


class SQLConvocatoriaRepository(ConvocatoriaRepository):
    """Implementación de ConvocatoriaRepository para base de datos relacional."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, orm: ConvocatoriaORM) -> Convocatoria:
        return Convocatoria(
            id=orm.id,
            fuente_id=orm.fuente_id,
            identificador_externo=orm.identificador_externo,
            titulo=orm.titulo,
            descripcion=orm.descripcion,
            url_detalle=HttpUrl(orm.url_detail) if orm.url_detail else None,
            fecha_apertura=orm.fecha_apertura,
            fecha_cierre=orm.fecha_cierre,
            monto=orm.monto,
            estado=orm.estado,
            metadatos=orm.metadatos,
            creado_en=orm.creado_en,
            actualizado_en=orm.actualizado_en,
        )

    async def get_by_fuente_and_externo(self, fuente_id: UUID, identificador_externo: str) -> Convocatoria | None:
        try:
            result = await self._session.execute(
                select(ConvocatoriaORM).where(
                    ConvocatoriaORM.fuente_id == fuente_id,
                    ConvocatoriaORM.identificador_externo == identificador_externo,
                )
            )
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar convocatoria externa: {e}"
            logger.error(msg, fuente_id=str(fuente_id), ext_id=identificador_externo, exc=e)
            raise PersistenceError(msg) from e

    async def get_all_by_fuente(self, fuente_id: UUID) -> list[Convocatoria]:
        try:
            result = await self._session.execute(select(ConvocatoriaORM).where(ConvocatoriaORM.fuente_id == fuente_id))
            orms = result.scalars().all()
            return [self._to_domain(orm) for orm in orms]
        except SQLAlchemyError as e:
            msg = f"Error al consultar todas las convocatorias para la fuente {fuente_id}: {e}"
            logger.error(msg, fuente_id=str(fuente_id), exc=e)
            raise PersistenceError(msg) from e

    async def save(self, convocatoria: Convocatoria) -> Convocatoria:
        try:
            result = await self._session.execute(
                select(ConvocatoriaORM).where(
                    ConvocatoriaORM.fuente_id == convocatoria.fuente_id,
                    ConvocatoriaORM.identificador_externo == convocatoria.identificador_externo,
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                orm = ConvocatoriaORM(
                    id=convocatoria.id,
                    fuente_id=convocatoria.fuente_id,
                    identificador_externo=convocatoria.identificador_externo,
                    titulo=convocatoria.titulo,
                    descripcion=convocatoria.descripcion,
                    url_detail=str(convocatoria.url_detalle) if convocatoria.url_detalle else None,
                    fecha_apertura=convocatoria.fecha_apertura,
                    fecha_cierre=convocatoria.fecha_cierre,
                    monto=convocatoria.monto,
                    estado=convocatoria.estado,
                    metadatos=convocatoria.metadatos,
                    creado_en=convocatoria.creado_en,
                    actualizado_en=convocatoria.actualizado_en,
                )
                self._session.add(orm)
            else:
                orm.titulo = convocatoria.titulo
                orm.descripcion = convocatoria.descripcion
                orm.url_detail = str(convocatoria.url_detalle) if convocatoria.url_detalle else None
                orm.fecha_apertura = convocatoria.fecha_apertura
                orm.fecha_cierre = convocatoria.fecha_cierre
                orm.monto = convocatoria.monto
                orm.estado = convocatoria.estado
                orm.metadatos = convocatoria.metadatos
                orm.actualizado_en = convocatoria.actualizado_en

            await self._session.flush()
            return self._to_domain(orm)
        except SQLAlchemyError as e:
            msg = f"Error al guardar convocatoria {convocatoria.titulo}: {e}"
            logger.error(msg, ext_id=convocatoria.identificador_externo, exc=e)
            raise PersistenceError(msg) from e

    async def save_evento_cambio(self, evento: EventoCambio, snapshot_id: UUID) -> EventoCambio:
        try:
            delta_json = [d.model_dump() for d in evento.deltas]
            orm = HistorialCambiosORM(
                id=evento.id,
                convocatoria_id=evento.convocatoria_id,
                snapshot_id=snapshot_id,
                fecha_deteccion=evento.fecha_deteccion,
                es_apertura=evento.tipo == "APERTURA",
                delta=delta_json,
                es_relevante=evento.es_relevante,
            )
            self._session.add(orm)
            await self._session.flush()
            return evento
        except SQLAlchemyError as e:
            msg = f"Error al registrar evento de cambio para convocatoria {evento.convocatoria_id}: {e}"
            logger.error(msg, convocatoria_id=str(evento.convocatoria_id), exc=e)
            raise PersistenceError(msg) from e

    async def flush(self) -> None:
        await self._session.flush()


class SQLNotificacionRepository(NotificacionRepository):
    """Implementación de NotificacionRepository para base de datos relacional."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, resultado: NotificacionResult) -> NotificacionResult:
        try:
            historial_result = await self._session.execute(
                select(HistorialCambiosORM).where(HistorialCambiosORM.id == resultado.evento_id)
            )
            historial_orm = historial_result.scalar_one_or_none()

            if not historial_orm:
                logger.warning(
                    "No se encontró historial_cambios para evento_id, saltando persistencia de notificación",
                    evento_id=str(resultado.evento_id),
                )
                return resultado

            orm = NotificacionORM(
                historial_cambios_id=resultado.evento_id,
                canal=resultado.canal,
                destinatario=resultado.destinatario,
                estado=resultado.estado,
                error_log=resultado.error_log,
            )
            self._session.add(orm)
            await self._session.flush()
            logger.info(
                "Notificación persistida",
                evento_id=str(resultado.evento_id),
                canal=resultado.canal,
                estado=resultado.estado,
            )
            return resultado
        except SQLAlchemyError as e:
            msg = f"Error al persistir notificación para evento {resultado.evento_id}: {e}"
            logger.error(msg, evento_id=str(resultado.evento_id), exc=e)
            raise PersistenceError(msg) from e
