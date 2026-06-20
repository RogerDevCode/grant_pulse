"""Modelos ORM de SQLAlchemy 2.0 — cross-database (SQLite / PostgreSQL)."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.infra.db.types import GUID


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uid() -> str:
    return str(uuid4())


class FuenteORM(Base):
    __tablename__ = "fuentes"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    url_base: Mapped[str] = mapped_column(String(500), nullable=False)
    configuracion_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    snapshots: Mapped[list["SnapshotORM"]] = relationship(
        "SnapshotORM", back_populates="fuente", cascade="all, delete-orphan"
    )
    convocatorias: Mapped[list["ConvocatoriaORM"]] = relationship(
        "ConvocatoriaORM", back_populates="fuente", cascade="all, delete-orphan"
    )


class SnapshotORM(Base):
    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    fuente_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("fuentes.id", ondelete="CASCADE"), nullable=False
    )
    fecha_captura: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    contenido_crudo: Mapped[str] = mapped_column(Text, nullable=False)
    screenshot_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_contenido: Mapped[str] = mapped_column(String(64), nullable=False)
    estado_ejecucion: Mapped[str] = mapped_column(String(50), nullable=False)
    metadatos: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    fuente: Mapped[FuenteORM] = relationship("FuenteORM", back_populates="snapshots")
    cambios_detectados: Mapped[list["HistorialCambiosORM"]] = relationship(
        "HistorialCambiosORM", back_populates="snapshot"
    )


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    fuente_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("fuentes.id", ondelete="SET NULL"), nullable=True
    )
    nivel: Mapped[str] = mapped_column(String(20), nullable=False)
    modulo: Mapped[str] = mapped_column(String(50), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    detalles: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConvocatoriaORM(Base):
    __tablename__ = "convocatorias"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    fuente_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("fuentes.id", ondelete="CASCADE"), nullable=False
    )
    identificador_externo: Mapped[str] = mapped_column(String(255), nullable=False)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_detail: Mapped[str | None] = mapped_column("url_detalle", String(500), nullable=True)
    fecha_apertura: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monto: Mapped[float | None] = mapped_column(Float, nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estado: Mapped[str] = mapped_column(String(100), nullable=False)
    metadatos: Mapped[dict[str, int | float | str | bool | None]] = mapped_column(JSON, nullable=False, default=dict)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    fuente: Mapped[FuenteORM] = relationship("FuenteORM", back_populates="convocatorias")
    historial_cambios: Mapped[list["HistorialCambiosORM"]] = relationship(
        "HistorialCambiosORM", back_populates="convocatoria", cascade="all, delete-orphan"
    )


class HistorialCambiosORM(Base):
    __tablename__ = "historial_cambios"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    convocatoria_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("convocatorias.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_deteccion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    es_apertura: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delta: Mapped[list[dict[str, str | None]]] = mapped_column(JSON, nullable=False, default=list)
    es_relevante: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    convocatoria: Mapped[ConvocatoriaORM] = relationship("ConvocatoriaORM", back_populates="historial_cambios")
    snapshot: Mapped[SnapshotORM] = relationship("SnapshotORM", back_populates="cambios_detectados")
    notificaciones: Mapped[list["NotificacionORM"]] = relationship(
        "NotificacionORM", back_populates="historial_cambio", cascade="all, delete-orphan"
    )


class NotificacionORM(Base):
    __tablename__ = "notificaciones"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    historial_cambios_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("historial_cambios.id", ondelete="CASCADE"), nullable=False
    )
    canal: Mapped[str] = mapped_column(String(50), nullable=False)
    destinatario: Mapped[str] = mapped_column(String(255), nullable=False)
    enviado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    historial_cambio: Mapped["HistorialCambiosORM"] = relationship("HistorialCambiosORM", back_populates="notificaciones")


class NotificacionConfigORM(Base):
    __tablename__ = "config_notificaciones"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    configuracion: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SuscripcionORM(Base):
    __tablename__ = "suscripciones"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=_uid)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    regiones: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    token_confirmacion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
