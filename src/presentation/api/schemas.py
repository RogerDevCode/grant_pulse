"""
Esquemas Pydantic para las respuestas de la API.
Mantienen los contratos HTTP aislados de las entidades de dominio puro.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class DeltaResponse(BaseModel):
    campo: str
    valor_anterior: str | None
    valor_nuevo: str | None


class EventoCambioResponse(BaseModel):
    id: UUID
    tipo: str
    es_relevante: bool
    fecha_deteccion: datetime
    deltas: list[DeltaResponse]


class ConvocatoriaResponse(BaseModel):
    id: UUID
    fuente_id: UUID
    fuente_nombre: str | None = None
    identificador_externo: str
    titulo: str
    descripcion: str | None
    url_detalle: HttpUrl
    fecha_apertura: datetime | None
    fecha_cierre: datetime | None
    monto: float | None
    estado: str
    actualizado_en: datetime


class ConvocatoriaDetailResponse(ConvocatoriaResponse):
    historial_cambios: list[EventoCambioResponse] = []


class NotificacionConfigCreate(BaseModel):
    nombre: str
    tipo: str
    configuracion: dict[str, Any]
    activa: bool = True


class NotificacionConfigResponse(NotificacionConfigCreate):
    id: UUID
    creado_en: datetime


class FuenteResponse(BaseModel):
    id: UUID
    nombre: str
    url_base: str
    activa: bool
    total_convocatorias: int = 0
    abiertas: int = 0
    cerradas: int = 0
    ultima_ejecucion: datetime | None = None
    creado_en: datetime
    actualizado_en: datetime


class FuenteToggleResponse(BaseModel):
    id: UUID
    nombre: str
    activa: bool


class DashboardStats(BaseModel):
    total_fuentes: int
    fuentes_activas: int
    total_convocatorias: int
    convocatorias_abiertas: int
    convocatorias_cerradas: int
    total_eventos: int
    eventos_relevantes: int


class AuditLogResponse(BaseModel):
    id: UUID
    fuente_id: UUID | None
    fuente_nombre: str | None = None
    nivel: str
    modulo: str
    mensaje: str
    detalles: dict[str, Any]
    creado_en: datetime


class NotificacionResponse(BaseModel):
    id: UUID
    canal: str
    destinatario: str
    estado: str
    enviado_en: datetime
    error_log: str | None
