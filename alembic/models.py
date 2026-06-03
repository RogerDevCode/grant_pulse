"""
Modelos ORM de SQLAlchemy 2.0 para PostgreSQL 17.
Define la estructura relacional de la base de datos de manera tipada y declarativa.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, NUMERIC, TIMESTAMP, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos ORM."""

    pass


class FuenteORM(Base):
    """Modelo ORM para la tabla 'fuentes'."""

    __tablename__ = "fuentes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    url_base: Mapped[str] = mapped_column(String(500), nullable=False)
    configuracion_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    activa: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relaciones
    snapshots: Mapped[list["SnapshotORM"]] = relationship(
        "SnapshotORM", back_populates="fuente", cascade="all, delete-orphan"
    )
    convocatorias: Mapped[list["ConvocatoriaORM"]] = relationship(
        "ConvocatoriaORM", back_populates="fuente", cascade="all, delete-orphan"
    )


class SnapshotORM(Base):
    """Modelo ORM para la tabla 'snapshots'."""

    __tablename__ = "snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fuente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuentes.id", ondelete="CASCADE"), nullable=False
    )
    fecha_captura: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))
    contenido_crudo: Mapped[str] = mapped_column(Text, nullable=False)
    hash_contenido: Mapped[str] = mapped_column(String(64), nullable=False)
    estado_ejecucion: Mapped[str] = mapped_column(String(50), nullable=False)
    metadatos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Relaciones
    fuente: Mapped[FuenteORM] = relationship("FuenteORM", back_populates="snapshots")
    cambios_detectados: Mapped[list["HistorialCambiosORM"]] = relationship(
        "HistorialCambiosORM", back_populates="snapshot"
    )


class AuditLogORM(Base):
    """Registro persistente de salud del sistema y errores de scraping/IA."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fuente_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuentes.id", ondelete="SET NULL"), nullable=True
    )
    nivel: Mapped[str] = mapped_column(String(20), nullable=False)  # INFO, WARNING, ERROR
    modulo: Mapped[str] = mapped_column(String(50), nullable=False)  # SCRAPER, LLM, REPO
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    detalles: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    creado_en: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))


class ConvocatoriaORM(Base):
    """Modelo ORM para la tabla 'convocatorias'."""

    __tablename__ = "convocatorias"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fuente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuentes.id", ondelete="CASCADE"), nullable=False
    )
    identificador_externo: Mapped[str] = mapped_column(String(255), nullable=False)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_detail: Mapped[str] = mapped_column("url_detalle", String(500), nullable=False)
    fecha_apertura: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    monto: Mapped[float | None] = mapped_column(NUMERIC(15, 2), nullable=True)
    estado: Mapped[str] = mapped_column(String(100), nullable=False)
    metadatos: Mapped[dict[str, int | float | str | bool | None]] = mapped_column(JSONB, nullable=False, default=dict)
    creado_en: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relaciones
    fuente: Mapped[FuenteORM] = relationship("FuenteORM", back_populates="convocatorias")
    historial_cambios: Mapped[list["HistorialCambiosORM"]] = relationship(
        "HistorialCambiosORM", back_populates="convocatoria", cascade="all, delete-orphan"
    )


class HistorialCambiosORM(Base):
    """Modelo ORM para la tabla 'historial_cambios'."""

    __tablename__ = "historial_cambios"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    convocatoria_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("convocatorias.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_deteccion: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))
    es_apertura: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    delta: Mapped[list[dict[str, str | None]]] = mapped_column(JSONB, nullable=False, default=list)
    es_relevante: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)

    # Relaciones
    convocatoria: Mapped[ConvocatoriaORM] = relationship("ConvocatoriaORM", back_populates="historial_cambios")
    snapshot: Mapped[SnapshotORM] = relationship("SnapshotORM", back_populates="cambios_detectados")
    notificaciones: Mapped[list["NotificacionORM"]] = relationship(
        "NotificacionORM", back_populates="historial_cambio", cascade="all, delete-orphan"
    )


class NotificacionORM(Base):
    """Modelo ORM para la tabla 'notificaciones'."""

    __tablename__ = "notificaciones"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    historial_cambios_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("historial_cambios.id", ondelete="CASCADE"), nullable=False
    )
    canal: Mapped[str] = mapped_column(String(50), nullable=False)
    destinatario: Mapped[str] = mapped_column(String(255), nullable=False)
    enviado_en: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    historial_cambio: Mapped[HistorialCambiosORM] = relationship("HistorialCambiosORM", back_populates="notificaciones")


class NotificacionConfigORM(Base):
    """Modelo ORM para almacenar configuraciones dinámicas de notificación (ej: Telegram, Email)."""

    __tablename__ = "config_notificaciones"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # TELEGRAM, EMAIL
    configuracion: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    activa: Mapped[bool] = mapped_column(BOOLEAN, default=True)
    creado_en: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))
