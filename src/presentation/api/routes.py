"""
Rutas HTTP de la API REST usando FastAPI.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from src.infra.db.models import (
    AuditLogORM,
    ConvocatoriaORM,
    FuenteORM,
    HistorialCambiosORM,
    NotificacionConfigORM,
    NotificacionORM,
    SnapshotORM,
)
from src.infra.logging import get_logger
from src.presentation.api.dependencies import DbSession
from src.presentation.api.schemas import (
    AuditLogResponse,
    ConvocatoriaDetailResponse,
    ConvocatoriaResponse,
    DashboardStats,
    DeltaResponse,
    EventoCambioResponse,
    FuenteResponse,
    FuenteToggleResponse,
    NotificacionConfigCreate,
    NotificacionConfigResponse,
    NotificacionResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["GrantPulse"])


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(session: DbSession) -> DashboardStats:
    total_fuentes = (await session.execute(select(func.count(FuenteORM.id)))).scalar() or 0
    fuentes_activas = (await session.execute(select(func.count(FuenteORM.id)).where(FuenteORM.activa.is_(True)))).scalar() or 0
    total_convocatorias = (await session.execute(select(func.count(ConvocatoriaORM.id)))).scalar() or 0
    convocatorias_abiertas = (
        await session.execute(select(func.count(ConvocatoriaORM.id)).where(ConvocatoriaORM.estado == "ABIERTO"))
    ).scalar() or 0
    convocatorias_cerradas = (
        await session.execute(select(func.count(ConvocatoriaORM.id)).where(ConvocatoriaORM.estado == "CERRADO"))
    ).scalar() or 0
    total_eventos = (await session.execute(select(func.count(HistorialCambiosORM.id)))).scalar() or 0
    eventos_relevantes = (
        await session.execute(select(func.count(HistorialCambiosORM.id)).where(HistorialCambiosORM.es_relevante.is_(True)))
    ).scalar() or 0
    return DashboardStats(
        total_fuentes=total_fuentes,
        fuentes_activas=fuentes_activas,
        total_convocatorias=total_convocatorias,
        convocatorias_abiertas=convocatorias_abiertas,
        convocatorias_cerradas=convocatorias_cerradas,
        total_eventos=total_eventos,
        eventos_relevantes=eventos_relevantes,
    )


@router.get("/fuentes", response_model=list[FuenteResponse])
async def list_fuentes(session: DbSession) -> list[FuenteResponse]:
    conv_subq = (
        select(
            ConvocatoriaORM.fuente_id,
            func.count(ConvocatoriaORM.id).label("total"),
            func.count(ConvocatoriaORM.id).filter(ConvocatoriaORM.estado == "ABIERTO").label("abiertas"),
            func.count(ConvocatoriaORM.id).filter(ConvocatoriaORM.estado == "CERRADO").label("cerradas"),
        )
        .group_by(ConvocatoriaORM.fuente_id)
        .subquery()
    )
    snap_subq = (
        select(
            SnapshotORM.fuente_id,
            func.max(SnapshotORM.fecha_captura).label("ultima_ejecucion"),
        )
        .group_by(SnapshotORM.fuente_id)
        .subquery()
    )
    stmt = (
        select(
            FuenteORM,
            func.coalesce(conv_subq.c.total, 0).label("total_convocatorias"),
            func.coalesce(conv_subq.c.abiertas, 0).label("abiertas"),
            func.coalesce(conv_subq.c.cerradas, 0).label("cerradas"),
            snap_subq.c.ultima_ejecucion,
        )
        .outerjoin(conv_subq, FuenteORM.id == conv_subq.c.fuente_id)
        .outerjoin(snap_subq, FuenteORM.id == snap_subq.c.fuente_id)
        .order_by(FuenteORM.nombre)
    )
    rows = (await session.execute(stmt)).all()
    return [
        FuenteResponse(
            id=f.id,
            nombre=f.nombre,
            url_base=f.url_base,
            activa=f.activa,
            total_convocatorias=int(total),
            abiertas=int(abi),
            cerradas=int(cer),
            ultima_ejecucion=last_snap,
            creado_en=f.creado_en,
            actualizado_en=f.actualizado_en,
        )
        for f, total, abi, cer, last_snap in rows
    ]


@router.patch("/fuentes/{fuente_id}/toggle", response_model=FuenteToggleResponse)
async def toggle_fuente(fuente_id: UUID, session: DbSession) -> FuenteToggleResponse:
    result = await session.execute(select(FuenteORM).where(FuenteORM.id == fuente_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")
    orm.activa = not orm.activa
    orm.actualizado_en = datetime.now(UTC)
    await session.flush()
    logger.info("Fuente toggled", fuente_id=str(orm.id), nombre=orm.nombre, activa=orm.activa)
    return FuenteToggleResponse(id=orm.id, nombre=orm.nombre, activa=orm.activa)


@router.get("/convocatorias", response_model=list[ConvocatoriaResponse])
async def list_convocatorias(
    session: DbSession,
    estado: str | None = Query(None, description="Filtrar por estado"),
    fuente_id: UUID | None = Query(None, description="Filtrar por ID de fuente"), # noqa: B008
    fuente_nombre: str | None = Query(None, description="Filtrar por nombre de fuente"),
    search: str | None = Query(None, description="Buscar en título"),
    orden: str | None = Query("actualizacion", description="Orden"),
    region: str | None = Query(None, description="Filtrar por región (Nacional, Metropolitana, etc.)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ConvocatoriaResponse]:
    fuente_ids_por_nombre: dict[str, UUID] = {}
    if fuente_nombre:
        fuente_rows = (await session.execute(
            select(FuenteORM.id, FuenteORM.nombre).where(FuenteORM.nombre.ilike(f"%{fuente_nombre}%"))
        )).all()
        if not fuente_rows:
            return []
        fuente_ids_por_nombre = {str(r.id): r.id for r in fuente_rows}

    query = select(ConvocatoriaORM)
    if estado:
        query = query.where(ConvocatoriaORM.estado == estado)
    if region:
        query = query.where(ConvocatoriaORM.region == region)
    if fuente_id:
        query = query.where(ConvocatoriaORM.fuente_id == fuente_id)
    elif fuente_ids_por_nombre:
        query = query.where(ConvocatoriaORM.fuente_id.in_(fuente_ids_por_nombre.values()))
    if search:
        query = query.where(ConvocatoriaORM.titulo.ilike(f"%{search}%"))

    if orden == "por_vencer":
        query = query.where(ConvocatoriaORM.fecha_cierre.isnot(None), ConvocatoriaORM.fecha_cierre >= datetime.now(UTC))
        query = query.order_by(ConvocatoriaORM.fecha_cierre.asc())
    elif orden == "recientes_creacion":
        query = query.order_by(ConvocatoriaORM.creado_en.desc())
    else:
        query = query.order_by(ConvocatoriaORM.actualizado_en.desc())

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    orms = result.scalars().all()
    fuentes_cache: dict[UUID, str] = {}
    response_list: list[ConvocatoriaResponse] = []
    for orm in orms:
        if orm.fuente_id not in fuentes_cache:
            fuente_result = await session.execute(select(FuenteORM.nombre).where(FuenteORM.id == orm.fuente_id))
            fuentes_cache[orm.fuente_id] = fuente_result.scalar_one_or_none() or "Desconocido"
        response_list.append(
            ConvocatoriaResponse(
                id=orm.id,
                fuente_id=orm.fuente_id,
                fuente_nombre=fuentes_cache[orm.fuente_id],
                identificador_externo=orm.identificador_externo,
                titulo=orm.titulo,
                descripcion=orm.descripcion,
                url_detalle=str(orm.url_detail) if orm.url_detail else "", # type: ignore[arg-type]
                fecha_apertura=orm.fecha_apertura,
                fecha_cierre=orm.fecha_cierre,
                monto=float(orm.monto) if orm.monto is not None else None,
                region=orm.region,
                estado=orm.estado,
                actualizado_en=orm.actualizado_en,
            )
        )
    return response_list


@router.get("/convocatorias/count")
async def count_convocatorias(
    session: DbSession,
    estado: str | None = Query(None),
    fuente_id: UUID | None = Query(None), # noqa: B008
    fuente_nombre: str | None = Query(None, description="Filtrar por nombre de fuente"),
    region: str | None = Query(None),
) -> dict[str, int]:
    fuente_ids_por_nombre: list[UUID] = []
    if fuente_nombre:
        fuente_rows = (await session.execute(
            select(FuenteORM.id).where(FuenteORM.nombre.ilike(f"%{fuente_nombre}%"))
        )).all()
        if not fuente_rows:
            return {"total": 0}
        fuente_ids_por_nombre = [r.id for r in fuente_rows]

    query = select(func.count(ConvocatoriaORM.id))
    if estado:
        query = query.where(ConvocatoriaORM.estado == estado)
    if fuente_id:
        query = query.where(ConvocatoriaORM.fuente_id == fuente_id)
    elif fuente_ids_por_nombre:
        query = query.where(ConvocatoriaORM.fuente_id.in_(fuente_ids_por_nombre))
    if region:
        query = query.where(ConvocatoriaORM.region == region)
    total = (await session.execute(query)).scalar() or 0
    return {"total": total}


@router.get("/convocatorias/{convocatoria_id}", response_model=ConvocatoriaDetailResponse)
async def get_convocatoria_detail(convocatoria_id: UUID, session: DbSession) -> ConvocatoriaDetailResponse:
    result = await session.execute(select(ConvocatoriaORM).where(ConvocatoriaORM.id == convocatoria_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada")
    fuente_result = await session.execute(select(FuenteORM.nombre).where(FuenteORM.id == orm.fuente_id))
    fuente_nombre = fuente_result.scalar_one_or_none() or "Desconocido"
    historial_result = await session.execute(
        select(HistorialCambiosORM).where(HistorialCambiosORM.convocatoria_id == convocatoria_id).order_by(HistorialCambiosORM.fecha_deteccion.desc())
    )
    historial_orms = historial_result.scalars().all()
    eventos: list[EventoCambioResponse] = []
    for h in historial_orms:
        deltas = [
            DeltaResponse(campo=str(d.get("campo", "")), valor_anterior=d.get("valor_anterior"), valor_nuevo=d.get("valor_nuevo"))
            for d in h.delta
        ]
        eventos.append(
            EventoCambioResponse(
                id=h.id,
                tipo="APERTURA" if h.es_apertura else "MODIFICACION",
                es_relevante=h.es_relevante,
                fecha_deteccion=h.fecha_deteccion,
                deltas=deltas,
            )
        )
    return ConvocatoriaDetailResponse(
        id=orm.id,
        fuente_id=orm.fuente_id,
        fuente_nombre=fuente_nombre,
        identificador_externo=orm.identificador_externo,
        titulo=orm.titulo,
        descripcion=orm.descripcion,
        url_detalle=str(orm.url_detail) if orm.url_detail else "",  # type: ignore[arg-type]
        fecha_apertura=orm.fecha_apertura,
        fecha_cierre=orm.fecha_cierre,
        monto=float(orm.monto) if orm.monto is not None else None,
        region=orm.region,
        estado=orm.estado,
        actualizado_en=orm.actualizado_en,
        historial_cambios=eventos,
    )


@router.delete("/convocatorias/{convocatoria_id}", status_code=204)
async def delete_convocatoria(convocatoria_id: UUID, session: DbSession) -> None:
    result = await session.execute(select(ConvocatoriaORM).where(ConvocatoriaORM.id == convocatoria_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada")
    await session.delete(orm)
    await session.flush()
    logger.info("Convocatoria eliminada", convocatoria_id=str(convocatoria_id))


@router.delete("/fuentes/{fuente_id}", status_code=204)
async def delete_fuente(fuente_id: UUID, session: DbSession) -> None:
    result = await session.execute(select(FuenteORM).where(FuenteORM.id == fuente_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")
    await session.delete(orm)
    await session.flush()
    logger.info("Fuente eliminada", fuente_id=str(fuente_id))


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    session: DbSession,
    nivel: str | None = Query(None),
    limite: int = Query(50, ge=1, le=200),
) -> list[AuditLogResponse]:
    query = select(AuditLogORM).order_by(AuditLogORM.creado_en.desc())
    if nivel:
        query = query.where(AuditLogORM.nivel == nivel)
    query = query.limit(limite)
    result = await session.execute(query)
    orms = result.scalars().all()
    fuentes_cache: dict[UUID, str] = {}
    resp: list[AuditLogResponse] = []
    for orm in orms:
        fnombre: str | None = None
        if orm.fuente_id:
            if orm.fuente_id not in fuentes_cache:
                fr = await session.execute(select(FuenteORM.nombre).where(FuenteORM.id == orm.fuente_id))
                fuentes_cache[orm.fuente_id] = fr.scalar_one_or_none() or "Desconocido"
            fnombre = fuentes_cache[orm.fuente_id]
        resp.append(
            AuditLogResponse(
                id=orm.id,
                fuente_id=orm.fuente_id,
                fuente_nombre=fnombre,
                nivel=orm.nivel,
                modulo=orm.modulo,
                mensaje=orm.mensaje,
                detalles=orm.detalles,
                creado_en=orm.creado_en,
            )
        )
    return resp


@router.get("/notificaciones", response_model=list[NotificacionResponse])
async def list_notificaciones(session: DbSession, limite: int = Query(50, ge=1, le=200)) -> list[NotificacionResponse]:
    result = await session.execute(select(NotificacionORM).order_by(NotificacionORM.enviado_en.desc()).limit(limite))
    orms = result.scalars().all()
    return [
        NotificacionResponse(
            id=orm.id,
            canal=orm.canal,
            destinatario=orm.destinatario,
            estado=orm.estado,
            enviado_en=orm.enviado_en,
            error_log=orm.error_log,
        )
        for orm in orms
    ]


@router.get("/config/notificaciones", response_model=list[NotificacionConfigResponse])
async def list_notification_configs(session: DbSession) -> list[NotificacionConfigResponse]:
    result = await session.execute(select(NotificacionConfigORM).order_by(NotificacionConfigORM.creado_en.desc()))
    orms = result.scalars().all()
    return [
        NotificacionConfigResponse(
            id=orm.id,
            nombre=orm.nombre,
            tipo=orm.tipo,
            configuracion=orm.configuracion,
            activa=orm.activa,
            creado_en=orm.creado_en,
        )
        for orm in orms
    ]


@router.post("/config/notificaciones", response_model=NotificacionConfigResponse)
async def create_notification_config(data: NotificacionConfigCreate, session: DbSession) -> NotificacionConfigResponse:
    orm = NotificacionConfigORM(
        nombre=data.nombre,
        tipo=data.tipo,
        configuracion=data.configuracion,
        activa=data.activa,
    )
    session.add(orm)
    await session.flush()
    logger.info("Config de notificación creada", config_id=str(orm.id), nombre=orm.nombre, tipo=orm.tipo)
    return NotificacionConfigResponse(
        id=orm.id,
        nombre=orm.nombre,
        tipo=orm.tipo,
        configuracion=orm.configuracion,
        activa=orm.activa,
        creado_en=orm.creado_en,
    )


@router.patch("/config/notificaciones/{config_id}/toggle", response_model=NotificacionConfigResponse)
async def toggle_notification_config(config_id: UUID, session: DbSession) -> NotificacionConfigResponse:
    result = await session.execute(select(NotificacionConfigORM).where(NotificacionConfigORM.id == config_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Configuración no encontrada")
    orm.activa = not orm.activa
    await session.flush()
    logger.info("Config de notificación toggled", config_id=str(orm.id), nombre=orm.nombre, activa=orm.activa)
    return NotificacionConfigResponse(
        id=orm.id,
        nombre=orm.nombre,
        tipo=orm.tipo,
        configuracion=orm.configuracion,
        activa=orm.activa,
        creado_en=orm.creado_en,
    )


@router.delete("/config/notificaciones/{config_id}", status_code=204)
async def delete_notification_config(config_id: UUID, session: DbSession) -> None:
    result = await session.execute(select(NotificacionConfigORM).where(NotificacionConfigORM.id == config_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Configuración no encontrada")
    await session.delete(orm)
    await session.flush()
    logger.info("Config de notificación eliminada", config_id=str(config_id))
