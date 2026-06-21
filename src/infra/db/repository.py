"""Repositorios SQLAlchemy — mapeo entidad↔ORM con auto-increment integer IDs."""


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


# ─── helpers ────────────────────────────────────────────────────────────

def _fuente_orm_to_entity(orm: FuenteORM) -> Fuente:
    try:
        rules_config = RulesConfig.model_validate_json(orm.configuracion_yaml)
    except Exception as e:
        logger.error("Error deserializando configuracion_yaml", fuente_id=orm.id, exc=e)
        raise PersistenceError(f"Error deserializando configuracion_yaml de fuente {orm.id}") from e
    return Fuente(
        id=orm.id,
        nombre=orm.nombre,
        url_base=HttpUrl(orm.url_base),
        configuracion_reglas=rules_config,
        activa=orm.activa,
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


def _convocatoria_orm_to_entity(orm: ConvocatoriaORM, fuente_nombre: str | None = None) -> Convocatoria:
    url_detail = HttpUrl(orm.url_detail) if orm.url_detail else None
    return Convocatoria(
        id=orm.id,
        fuente_id=orm.fuente_id,
        identificador_externo=orm.identificador_externo,
        titulo=orm.titulo,
        descripcion=orm.descripcion,
        url_detalle=url_detail,
        fecha_apertura=orm.fecha_apertura,
        fecha_cierre=orm.fecha_cierre,
        monto=orm.monto,
        region=orm.region,
        estado=orm.estado,
        metadatos=orm.metadatos,
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


def _snapshot_orm_to_entity(orm: SnapshotORM) -> Snapshot:
    return Snapshot(
        id=orm.id,
        fuente_id=orm.fuente_id,
        fecha_captura=orm.fecha_captura,
        contenido_crudo=orm.contenido_crudo,
        screenshot_b64=orm.screenshot_b64,
        hash_contenido=orm.hash_contenido,
        estado_ejecucion=orm.estado_ejecucion,
    )


# ─── SQLFuenteRepository ────────────────────────────────────────────────

class SQLFuenteRepository(FuenteRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, fuente_id: int) -> Fuente | None:
        try:
            orm = await self._session.get(FuenteORM, fuente_id)
            return _fuente_orm_to_entity(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar fuente por id {fuente_id}: {e}"
            logger.error(msg, fuente_id=fuente_id, exc=e)
            raise PersistenceError(msg) from e

    async def get_by_nombre(self, nombre: str) -> Fuente | None:
        try:
            result = await self._session.execute(select(FuenteORM).where(FuenteORM.nombre == nombre))
            orm = result.scalar_one_or_none()
            return _fuente_orm_to_entity(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar fuente por nombre {nombre}: {e}"
            logger.error(msg, nombre=nombre, exc=e)
            raise PersistenceError(msg) from e

    async def get_all_active(self) -> list[Fuente]:
        try:
            result = await self._session.execute(select(FuenteORM).where(FuenteORM.activa.is_(True)))
            return [_fuente_orm_to_entity(orm) for orm in result.scalars().all()]
        except SQLAlchemyError as e:
            msg = f"Error al consultar fuentes activas: {e}"
            logger.error(msg, exc=e)
            raise PersistenceError(msg) from e

    async def get_all(self) -> list[Fuente]:
        try:
            result = await self._session.execute(select(FuenteORM))
            return [_fuente_orm_to_entity(orm) for orm in result.scalars().all()]
        except SQLAlchemyError as e:
            msg = f"Error al consultar todas las fuentes: {e}"
            logger.error(msg, exc=e)
            raise PersistenceError(msg) from e

    async def save(self, fuente: Fuente) -> Fuente:
        try:
            if fuente.id is not None:
                result = await self._session.execute(select(FuenteORM).where(FuenteORM.id == fuente.id))
                orm = result.scalar_one_or_none()
            else:
                orm = None

            config_json = fuente.configuracion_reglas.model_dump_json()

            if not orm:
                orm = FuenteORM(
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
            if fuente.id is None:
                fuente = fuente.model_copy(update={"id": orm.id})
            return fuente
        except SQLAlchemyError as e:
            msg = f"Error al guardar fuente: {e}"
            logger.error(msg, fuente_nombre=fuente.nombre, exc=e)
            raise PersistenceError(msg) from e


# ─── SQLSnapshotRepository ──────────────────────────────────────────────

class SQLSnapshotRepository(SnapshotRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, snapshot: Snapshot) -> Snapshot:
        try:
            orm = SnapshotORM(
                fuente_id=snapshot.fuente_id,
                fecha_captura=snapshot.fecha_captura,
                contenido_crudo=snapshot.contenido_crudo,
                screenshot_b64=snapshot.screenshot_b64,
                hash_contenido=snapshot.hash_contenido,
                estado_ejecucion=snapshot.estado_ejecucion,
            )
            self._session.add(orm)
            await self._session.flush()
            await self._session.refresh(orm)
            
            if getattr(orm, "id", None) is None:
                msg = f"CRÍTICO: orm.id es None después de flush y refresh. orm={orm.__dict__}"
                logger.error(msg)
                raise PersistenceError(msg)
                
            return snapshot.model_copy(update={"id": orm.id})
        except SQLAlchemyError as e:
            msg = f"Error al guardar snapshot: {e}"
            logger.error(msg, fuente_id=snapshot.fuente_id, exc=e)
            raise PersistenceError(msg) from e

    async def get_latest_by_fuente(self, fuente_id: int) -> Snapshot | None:
        try:
            result = await self._session.execute(
                select(SnapshotORM)
                .where(SnapshotORM.fuente_id == fuente_id)
                .order_by(SnapshotORM.fecha_captura.desc())
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            return _snapshot_orm_to_entity(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar último snapshot de fuente {fuente_id}: {e}"
            logger.error(msg, fuente_id=fuente_id, exc=e)
            raise PersistenceError(msg) from e


# ─── SQLConvocatoriaRepository ─────────────────────────────────────────

class SQLConvocatoriaRepository(ConvocatoriaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_fuente_and_externo(self, fuente_id: int, identificador_externo: str) -> Convocatoria | None:
        try:
            result = await self._session.execute(
                select(ConvocatoriaORM).where(
                    ConvocatoriaORM.fuente_id == fuente_id,
                    ConvocatoriaORM.identificador_externo == identificador_externo,
                )
            )
            orm = result.scalar_one_or_none()
            return _convocatoria_orm_to_entity(orm) if orm else None
        except SQLAlchemyError as e:
            msg = f"Error al consultar convocatoria por externo {identificador_externo}: {e}"
            logger.error(msg, ext_id=identificador_externo, exc=e)
            raise PersistenceError(msg) from e

    async def get_all_by_fuente(self, fuente_id: int) -> list[Convocatoria]:
        try:
            result = await self._session.execute(
                select(ConvocatoriaORM).where(ConvocatoriaORM.fuente_id == fuente_id)
            )
            return [_convocatoria_orm_to_entity(orm) for orm in result.scalars().all()]
        except SQLAlchemyError as e:
            msg = f"Error al consultar convocatorias por fuente {fuente_id}: {e}"
            logger.error(msg, fuente_id=fuente_id, exc=e)
            raise PersistenceError(msg) from e

    async def save(self, convocatoria: Convocatoria) -> Convocatoria:
        try:
            if convocatoria.identificador_externo and convocatoria.fuente_id:
                result = await self._session.execute(
                    select(ConvocatoriaORM).where(
                        ConvocatoriaORM.fuente_id == convocatoria.fuente_id,
                        ConvocatoriaORM.identificador_externo == convocatoria.identificador_externo,
                    )
                )
                orm = result.scalars().first()
            else:
                orm = None

            if not orm:
                orm = ConvocatoriaORM(
                    fuente_id=convocatoria.fuente_id,
                    identificador_externo=convocatoria.identificador_externo,
                    titulo=convocatoria.titulo,
                    descripcion=convocatoria.descripcion,
                    url_detail=str(convocatoria.url_detalle) if convocatoria.url_detalle else None,
                    fecha_apertura=convocatoria.fecha_apertura,
                    fecha_cierre=convocatoria.fecha_cierre,
                    monto=convocatoria.monto,
                    region=convocatoria.region,
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
                orm.region = convocatoria.region
                orm.estado = convocatoria.estado
                orm.metadatos = convocatoria.metadatos
                orm.actualizado_en = convocatoria.actualizado_en

            await self._session.flush()
            if convocatoria.id is None:
                await self._session.refresh(orm)
                convocatoria = convocatoria.model_copy(update={"id": orm.id})
            return convocatoria
        except SQLAlchemyError as e:
            msg = f"Error al guardar convocatoria {convocatoria.identificador_externo}: {e}"
            logger.error(msg, ext_id=convocatoria.identificador_externo, exc=e)
            raise PersistenceError(msg) from e

    async def save_evento_cambio(self, evento: EventoCambio, snapshot_id: int) -> EventoCambio:
        try:
            delta_json = [d.model_dump() for d in evento.deltas]
            orm = HistorialCambiosORM(
                convocatoria_id=evento.convocatoria_id,
                snapshot_id=snapshot_id,
                fecha_deteccion=evento.fecha_deteccion,
                es_apertura=evento.tipo == "APERTURA",
                delta=delta_json,
                es_relevante=evento.es_relevante,
            )
            self._session.add(orm)
            await self._session.flush()
            await self._session.refresh(orm)
            return evento.model_copy(update={"id": orm.id})
        except SQLAlchemyError as e:
            msg = f"Error al registrar evento de cambio para convocatoria {evento.convocatoria_id}: {e}"
            logger.error(msg, convocatoria_id=evento.convocatoria_id, exc=e)
            raise PersistenceError(msg) from e

    async def flush(self) -> None:
        try:
            await self._session.flush()
        except SQLAlchemyError as e:
            msg = f"Error en flush de convocatorias: {e}"
            logger.error(msg, exc=e)
            raise PersistenceError(msg) from e


# ─── SQLNotificacionRepository ──────────────────────────────────────────

class SQLNotificacionRepository(NotificacionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, resultado: NotificacionResult) -> NotificacionResult:
        try:
            if resultado.evento_id:
                result = await self._session.execute(
                    select(HistorialCambiosORM).where(HistorialCambiosORM.id == resultado.evento_id)
                )
                if not result.scalar_one_or_none():
                    msg = f"Evento de cambio {resultado.evento_id} no encontrado"
                    raise PersistenceError(msg)

            orm = NotificacionORM(
                historial_cambios_id=resultado.evento_id,
                canal=resultado.canal,
                destinatario=resultado.destinatario,
                estado=resultado.estado,
                error_log=resultado.error_log,
            )
            self._session.add(orm)
            await self._session.flush()
            return resultado
        except SQLAlchemyError as e:
            msg = f"Error al guardar notificación: {e}"
            logger.error(msg, exc=e)
            raise PersistenceError(msg) from e
