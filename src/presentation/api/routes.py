"""
Rutas HTTP de la API REST usando FastAPI.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy import and_, delete, func, select

from src.infra.db.models import (
    AuditLogORM,
    ConvocatoriaORM,
    FuenteORM,
    HistorialCambiosORM,
    NotificacionConfigORM,
    NotificacionORM,
    SnapshotORM,
    SuscripcionORM,
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
    SuscripcionCreate,
    SuscripcionResponse,
    SuscripcionUpdate,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["GrantPulse"])


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(session: DbSession) -> DashboardStats:
    total_fuentes = (await session.execute(select(func.count(FuenteORM.id)))).scalar() or 0
    fuentes_activas = (
        await session.execute(select(func.count(FuenteORM.id)).where(FuenteORM.activa.is_(True)))
    ).scalar() or 0
    total_convocatorias = (await session.execute(select(func.count(ConvocatoriaORM.id)))).scalar() or 0
    convocatorias_abiertas = (
        await session.execute(select(func.count(ConvocatoriaORM.id)).where(ConvocatoriaORM.estado == "ABIERTO"))
    ).scalar() or 0
    convocatorias_cerradas = (
        await session.execute(select(func.count(ConvocatoriaORM.id)).where(ConvocatoriaORM.estado == "CERRADO"))
    ).scalar() or 0
    total_eventos = (await session.execute(select(func.count(HistorialCambiosORM.id)))).scalar() or 0
    eventos_relevantes = (
        await session.execute(
            select(func.count(HistorialCambiosORM.id)).where(HistorialCambiosORM.es_relevante.is_(True))
        )
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


@router.get("/debug/report")
async def get_logs_report() -> dict[str, str]:
    import glob

    reports = glob.glob("reports/quality_report_*.md")
    if not reports:
        return {"error": "No reports found"}
    latest = max(reports)
    with open(latest) as f:
        return {"content": f.read()}


@router.get("/debug/errors")
async def get_errors_log() -> dict[str, str]:
    """Retorna el contenido de data/errors.log"""
    log_path = Path("data/errors.log")
    if not log_path.exists():
        return {"error": "No errors.log found"}
    try:
        content = log_path.read_text(encoding="utf-8")
        return {"content": content}
    except Exception as e:
        logger.error("Error al leer errors.log", exc=e)
        return {"error": str(e)}


@router.delete("/debug/errors", status_code=204)
async def clear_errors_log() -> None:
    """Borra el contenido de data/errors.log"""
    log_path = Path("data/errors.log")
    if log_path.exists():
        try:
            log_path.write_text("", encoding="utf-8")
            logger.info("Archivo errors.log limpiado por el usuario")
        except Exception as e:
            logger.error("Error al limpiar errors.log", exc=e)
            raise HTTPException(status_code=500, detail="No se pudo limpiar el log") from e


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
async def toggle_fuente(fuente_id: int, session: DbSession) -> FuenteToggleResponse:
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
    fuente_id: int | None = Query(None, description="Filtrar por ID de fuente"),  # noqa: B008
    fuente_nombre: str | None = Query(None, description="Filtrar por nombre de fuente"),
    search: str | None = Query(None, description="Buscar en título"),
    orden: str | None = Query("actualizacion", description="Orden"),
    region: str | None = Query(None, description="Filtrar por región (Nacional, Metropolitana, etc.)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ConvocatoriaResponse]:
    fuente_ids_por_nombre: dict[str, int] = {}
    if fuente_nombre:
        fuente_rows = (
            await session.execute(
                select(FuenteORM.id, FuenteORM.nombre).where(FuenteORM.nombre.ilike(f"%{fuente_nombre}%"))
            )
        ).all()
        if not fuente_rows:
            return []
        fuente_ids_por_nombre = {str(r.id): r.id for r in fuente_rows}

    query = select(ConvocatoriaORM, FuenteORM.nombre).join(FuenteORM, ConvocatoriaORM.fuente_id == FuenteORM.id)
    if estado:
        query = query.where(ConvocatoriaORM.estado == estado)
    if region:
        from sqlalchemy import String
        region_search = region.replace("á", "%").replace("é", "%").replace("í", "%").replace("ó", "%").replace("ú", "%")
        region_search = region_search.replace("Á", "%").replace("É", "%").replace("Í", "%").replace("Ó", "%").replace("Ú", "%")
        query = query.where(ConvocatoriaORM.regiones.cast(String).ilike(f"%{region_search}%"))
    if fuente_id:
        query = query.where(ConvocatoriaORM.fuente_id == fuente_id)
    elif fuente_ids_por_nombre:
        query = query.where(ConvocatoriaORM.fuente_id.in_(fuente_ids_por_nombre.values()))
    if search:
        query = query.where(ConvocatoriaORM.titulo.ilike(f"%{search}%"))

    if orden == "por_vencer":
        # Ordenar primero las que vencen en el futuro (ascendente),
        # luego las vencidas, y al final las sin fecha (nullslast).
        now = datetime.now(UTC)
        query = query.order_by(
            # Si ya venció (fecha_cierre < now), le damos prioridad 1 (va al final). Si no, prioridad 0 (va al inicio)
            # Para SQL Standard y Postgres:
            func.coalesce(ConvocatoriaORM.fecha_cierre < now, False).asc(),
            ConvocatoriaORM.fecha_cierre.asc().nullslast()
        )
    elif orden == "recientes_creacion":
        query = query.order_by(ConvocatoriaORM.creado_en.desc())
    else:
        query = query.order_by(ConvocatoriaORM.actualizado_en.desc())

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    rows = result.all()
    return [
        ConvocatoriaResponse(
            id=orm.id,
            fuente_id=orm.fuente_id,
            fuente_nombre=fuente_nombre,
            identificador_externo=orm.identificador_externo,
            titulo=orm.titulo,
            descripcion=orm.descripcion,
            url_detalle=orm.url_detail,
            fecha_apertura=orm.fecha_apertura,
            fecha_cierre=orm.fecha_cierre,
            monto=float(orm.monto) if orm.monto is not None else None,
            regiones=orm.regiones,
            estado=orm.estado,
            actualizado_en=orm.actualizado_en,
        )
        for orm, fuente_nombre in rows
    ]


@router.get("/convocatorias/filtradas")
async def list_convocatorias_filtradas(
    session: DbSession,
    activo: bool | None = Query(None, description="Filtrar por convocatorias vigentes (ABIERTO) y fuentes activas"),
    institucion: str | None = Query(None, description="Filtrar por nombre de la institución (fuente)"),
    region: str | None = Query(None, description="Filtrar por región asociada"),
    limit: int = Query(500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Endpoint simple para recuperar convocatorias filtradas en formato JSON puro.
    Permite contrastar los datos de Postgres con el frontend.
    """
    from sqlalchemy import String, and_

    query = select(ConvocatoriaORM, FuenteORM.nombre, FuenteORM.activa).join(
        FuenteORM, ConvocatoriaORM.fuente_id == FuenteORM.id
    )

    if activo is not None:
        if activo:
            query = query.where(
                and_(
                    ConvocatoriaORM.estado == "ABIERTO",
                    FuenteORM.activa.is_(True)
                )
            )
        else:
            query = query.where(
                (ConvocatoriaORM.estado != "ABIERTO") | (FuenteORM.activa.is_(False))
            )

    if institucion:
        query = query.where(FuenteORM.nombre.ilike(f"%{institucion}%"))

    if region:
        region_search = region.replace("á", "%").replace("é", "%").replace("í", "%").replace("ó", "%").replace("ú", "%")
        region_search = region_search.replace("Á", "%").replace("É", "%").replace("Í", "%").replace("Ó", "%").replace("Ú", "%")
        query = query.where(ConvocatoriaORM.regiones.cast(String).ilike(f"%{region_search}%"))

    query = query.order_by(ConvocatoriaORM.actualizado_en.desc()).limit(limit)

    result = await session.execute(query)
    rows = result.all()

    return [
        {
            "id": orm.id,
            "fuente_id": orm.fuente_id,
            "fuente_nombre": fuente_nombre,
            "fuente_activa": fuente_activa,
            "identificador_externo": orm.identificador_externo,
            "titulo": orm.titulo,
            "descripcion": orm.descripcion,
            "url_detalle": orm.url_detail,
            "fecha_apertura": orm.fecha_apertura.isoformat() if orm.fecha_apertura else None,
            "fecha_cierre": orm.fecha_cierre.isoformat() if orm.fecha_cierre else None,
            "monto": float(orm.monto) if orm.monto is not None else None,
            "regiones": orm.regiones,
            "estado": orm.estado,
            "actualizado_en": orm.actualizado_en.isoformat() if orm.actualizado_en else None,
        }
        for orm, fuente_nombre, fuente_activa in rows
    ]


@router.get("/convocatorias/count")
async def count_convocatorias(
    session: DbSession,
    estado: str | None = Query(None),
    fuente_id: int | None = Query(None),  # noqa: B008
    fuente_nombre: str | None = Query(None, description="Filtrar por nombre de fuente"),
    region: str | None = Query(None),
    search: str | None = Query(None, description="Buscar por término en título"),
) -> dict[str, int]:
    fuente_ids_por_nombre: list[int] = []
    if fuente_nombre:
        fuente_rows = (
            await session.execute(select(FuenteORM.id).where(FuenteORM.nombre.ilike(f"%{fuente_nombre}%")))
        ).all()
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
        from sqlalchemy import String
        region_search = region.replace("á", "%").replace("é", "%").replace("í", "%").replace("ó", "%").replace("ú", "%")
        region_search = region_search.replace("Á", "%").replace("É", "%").replace("Í", "%").replace("Ó", "%").replace("Ú", "%")
        query = query.where(ConvocatoriaORM.regiones.cast(String).ilike(f"%{region_search}%"))
    if search:
        query = query.where(ConvocatoriaORM.titulo.ilike(f"%{search}%"))
    total = (await session.execute(query)).scalar() or 0
    return {"total": total}


@router.get("/convocatorias/kpi")
async def get_convocatorias_kpi(
    session: DbSession,
    estado: str | None = Query(None),
    fuente_id: int | None = Query(None),  # noqa: B008
    fuente_nombre: str | None = Query(None, description="Filtrar por nombre de fuente"),
    region: str | None = Query(None),
    search: str | None = Query(None, description="Buscar por término en título"),
) -> dict[str, int]:
    fuente_ids_por_nombre: list[int] = []
    if fuente_nombre:
        fuente_rows = (
            await session.execute(select(FuenteORM.id).where(FuenteORM.nombre.ilike(f"%{fuente_nombre}%")))
        ).all()
        if not fuente_rows:
            return {"abiertas": 0, "permanentes": 0, "vencen_30": 0, "instituciones": 0, "sin_fecha": 0}
        fuente_ids_por_nombre = [r.id for r in fuente_rows]

    now = datetime.now(UTC)
    filters = []
    if estado:
        filters.append(ConvocatoriaORM.estado == estado)
    if fuente_id:
        filters.append(ConvocatoriaORM.fuente_id == fuente_id)
    elif fuente_ids_por_nombre:
        filters.append(ConvocatoriaORM.fuente_id.in_(fuente_ids_por_nombre))
    if region:
        from sqlalchemy import String
        region_search = region.replace("á", "%").replace("é", "%").replace("í", "%").replace("ó", "%").replace("ú", "%")
        region_search = region_search.replace("Á", "%").replace("É", "%").replace("Í", "%").replace("Ó", "%").replace("Ú", "%")
        filters.append(ConvocatoriaORM.regiones.cast(String).ilike(f"%{region_search}%"))
    if search:
        filters.append(ConvocatoriaORM.titulo.ilike(f"%{search}%"))

    abiertas_q = select(func.count(ConvocatoriaORM.id)).where(ConvocatoriaORM.estado == "ABIERTO")
    if filters:
        abiertas_q = abiertas_q.where(and_(*filters))
    abiertas = (await session.execute(abiertas_q)).scalar() or 0

    permanentes_q = select(func.count(ConvocatoriaORM.id)).where(ConvocatoriaORM.estado == "PERMANENTE")
    if filters:
        permanentes_q = permanentes_q.where(and_(*filters))
    permanentes = (await session.execute(permanentes_q)).scalar() or 0

    vencen_30_q = select(func.count(ConvocatoriaORM.id)).where(
        ConvocatoriaORM.estado == "ABIERTO",
        ConvocatoriaORM.fecha_cierre.isnot(None),
        ConvocatoriaORM.fecha_cierre >= now,
        ConvocatoriaORM.fecha_cierre <= now + timedelta(days=30),
    )
    vencen_30_count = (await session.execute(vencen_30_q)).scalar() or 0

    inst_q = select(func.count(func.distinct(ConvocatoriaORM.fuente_id))).where(ConvocatoriaORM.estado == "ABIERTO")
    if filters:
        inst_q = inst_q.where(and_(*filters))
    instituciones = (await session.execute(inst_q)).scalar() or 0

    sin_fecha_q = select(func.count(ConvocatoriaORM.id)).where(
        ConvocatoriaORM.estado == "ABIERTO",
        ConvocatoriaORM.fecha_cierre.is_(None),
    )
    if filters:
        sin_fecha_q = sin_fecha_q.where(and_(*filters))
    sin_fecha = (await session.execute(sin_fecha_q)).scalar() or 0

    return {
        "abiertas": abiertas,
        "permanentes": permanentes,
        "vencen_30": vencen_30_count,
        "instituciones": instituciones,
        "sin_fecha": sin_fecha,
    }


@router.get("/convocatorias/{convocatoria_id}", response_model=ConvocatoriaDetailResponse)
async def get_convocatoria_detail(convocatoria_id: int, session: DbSession) -> ConvocatoriaDetailResponse:
    result = await session.execute(select(ConvocatoriaORM).where(ConvocatoriaORM.id == convocatoria_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada")
    fuente_result = await session.execute(select(FuenteORM.nombre).where(FuenteORM.id == orm.fuente_id))
    fuente_nombre = fuente_result.scalar_one_or_none() or "Desconocido"
    historial_result = await session.execute(
        select(HistorialCambiosORM)
        .where(HistorialCambiosORM.convocatoria_id == convocatoria_id)
        .order_by(HistorialCambiosORM.fecha_deteccion.desc())
    )
    historial_orms = historial_result.scalars().all()
    eventos: list[EventoCambioResponse] = []
    for h in historial_orms:
        deltas = [
            DeltaResponse(
                campo=str(d.get("campo", "")), valor_anterior=d.get("valor_anterior"), valor_nuevo=d.get("valor_nuevo")
            )
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
        url_detalle=orm.url_detail,  # type: ignore[arg-type]
        fecha_apertura=orm.fecha_apertura,
        fecha_cierre=orm.fecha_cierre,
        monto=float(orm.monto) if orm.monto is not None else None,
        regiones=orm.regiones,
        estado=orm.estado,
        actualizado_en=orm.actualizado_en,
        historial_cambios=eventos,
    )


@router.delete("/convocatorias/{convocatoria_id}", status_code=204)
async def delete_convocatoria(convocatoria_id: int, session: DbSession) -> None:
    result = await session.execute(select(ConvocatoriaORM).where(ConvocatoriaORM.id == convocatoria_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada")
    await session.delete(orm)
    await session.flush()
    logger.info("Convocatoria eliminada", convocatoria_id=str(convocatoria_id))


@router.delete("/fuentes/{fuente_id}", status_code=204)
async def delete_fuente(fuente_id: int, session: DbSession) -> None:
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
    fuentes_cache: dict[int, str] = {}
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
async def toggle_notification_config(config_id: int, session: DbSession) -> NotificacionConfigResponse:
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
async def delete_notification_config(config_id: int, session: DbSession) -> None:
    result = await session.execute(select(NotificacionConfigORM).where(NotificacionConfigORM.id == config_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Configuración no encontrada")
    await session.delete(orm)
    await session.flush()
    logger.info("Config de notificación eliminada", config_id=str(config_id))


# ─── SUSCRIPCIONES ──────────────────────────────────────────────────────────


@router.get("/suscripciones/regiones")
async def list_regiones_suscripcion() -> dict[str, list[str]]:
    """Retorna la lista de regiones disponibles para suscripción."""
    from src.core.domain.entities import REGIONES_CHILE  # noqa: PLC0415

    return {"regiones": list(REGIONES_CHILE)}


@router.post("/suscripciones", response_model=SuscripcionResponse, status_code=201)
async def crear_suscripcion(data: SuscripcionCreate, session: DbSession) -> SuscripcionResponse:
    # Validar que al menos una región esté seleccionada
    if not data.regiones:
        raise HTTPException(status_code=422, detail="Debe seleccionar al menos una región")

    # Validar que el chat_id no esté vacío
    if not data.chat_id or not data.chat_id.strip():
        raise HTTPException(status_code=422, detail="chat_id es requerido")

    # Buscar suscripción existente por chat_id
    result = await session.execute(select(SuscripcionORM).where(SuscripcionORM.chat_id == data.chat_id.strip()))
    existente = result.scalar_one_or_none()

    if existente:
        # Actualizar: agregar nuevas regiones a las existentes
        regiones_actuales = set(existente.regiones or [])
        regiones_actuales.update(data.regiones)
        existente.regiones = list(regiones_actuales)
        existente.activa = True
        existente.actualizado_en = datetime.now(UTC)
        await session.flush()
        logger.info("Suscripción actualizada", chat_id=data.chat_id, regiones=existente.regiones)
        orm = existente
    else:
        orm = SuscripcionORM(
            chat_id=data.chat_id.strip(),
            nombre=data.nombre,
            regiones=data.regiones,
            activa=True,
            confirmado=True,
        )
        session.add(orm)
        await session.flush()
        logger.info("Suscripción creada", chat_id=data.chat_id, regiones=data.regiones)

    return SuscripcionResponse(
        id=orm.id,
        chat_id=orm.chat_id,
        nombre=orm.nombre,
        regiones=orm.regiones,
        activa=orm.activa,
        confirmado=orm.confirmado,
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


@router.get("/suscripciones/{chat_id}", response_model=SuscripcionResponse)
async def obtener_suscripcion(chat_id: str, session: DbSession) -> SuscripcionResponse:
    result = await session.execute(select(SuscripcionORM).where(SuscripcionORM.chat_id == chat_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    return SuscripcionResponse(
        id=orm.id,
        chat_id=orm.chat_id,
        nombre=orm.nombre,
        regiones=orm.regiones,
        activa=orm.activa,
        confirmado=orm.confirmado,
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


@router.patch("/suscripciones/{suscripcion_id}", response_model=SuscripcionResponse)
async def actualizar_suscripcion(
    suscripcion_id: int, data: SuscripcionUpdate, session: DbSession
) -> SuscripcionResponse:
    result = await session.execute(select(SuscripcionORM).where(SuscripcionORM.id == suscripcion_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    if data.regiones is not None:
        orm.regiones = data.regiones
    if data.nombre is not None:
        orm.nombre = data.nombre
    if data.activa is not None:
        orm.activa = data.activa
    orm.actualizado_en = datetime.now(UTC)
    await session.flush()
    return SuscripcionResponse(
        id=orm.id,
        chat_id=orm.chat_id,
        nombre=orm.nombre,
        regiones=orm.regiones,
        activa=orm.activa,
        confirmado=orm.confirmado,
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


@router.delete("/suscripciones/{suscripcion_id}", status_code=204)
async def eliminar_suscripcion(suscripcion_id: int, session: DbSession) -> None:
    result = await session.execute(select(SuscripcionORM).where(SuscripcionORM.id == suscripcion_id))
    orm = result.scalar_one_or_none()
    if not orm:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    await session.delete(orm)
    await session.flush()
    logger.info("Suscripción eliminada", suscripcion_id=str(suscripcion_id))


# ─── SCRAPE MANUAL ─────────────────────────────────────────────────────
# Guardia para evitar múltiples scrapeos simultáneos
_scrape_en_curso: bool = False


async def _ejecutar_scrape() -> None:
    """Corre run_all_active_sources() en background."""
    global _scrape_en_curso  # noqa: PLW0603
    try:
        from src.infra.cli import run_all_active_sources  # noqa: PLC0415

        await run_all_active_sources()
    except Exception as exc:
        logger.error("Scrape manual falló", exc=exc)
        import traceback

        with open("data/errors.log", "a") as f:
            f.write(f"Scrape manual falló globalmente: {exc}\n{traceback.format_exc()}\n")
    finally:
        _scrape_en_curso = False


@router.post("/scrape", status_code=202)
async def trigger_scrape(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Dispara scraping manual de todas las fuentes activas en background."""
    global _scrape_en_curso  # noqa: PLW0603
    if _scrape_en_curso:
        raise HTTPException(status_code=409, detail="Ya hay un scrape en curso")
    _scrape_en_curso = True
    background_tasks.add_task(_ejecutar_scrape)
    logger.info("Scrape manual disparado")
    return {"status": "iniciado", "message": "Scrape iniciado en segundo plano"}


@router.get("/scrape/status")
async def get_scrape_status() -> dict[str, bool]:
    """Devuelve el estado actual del scraping manual."""
    return {"en_curso": _scrape_en_curso}




@router.delete("/debug/wipe", status_code=204)
async def debug_wipe_data(session: DbSession) -> None:
    """Borra todos los proyectos y datos relacionados (solo debug)."""
    try:
        await session.execute(delete(HistorialCambiosORM))
        await session.execute(delete(NotificacionORM))
        await session.execute(delete(ConvocatoriaORM))
        await session.execute(delete(SnapshotORM))
        await session.commit()
        logger.warning("Debug wipe: Se borraron todos los datos de convocatorias y snapshots")
    except Exception as e:
        await session.rollback()
        logger.error("Error en debug wipe", exc=e)
        raise HTTPException(status_code=500, detail="Error al limpiar datos") from e
