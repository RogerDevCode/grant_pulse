"""Initial schema with auto-increment integer primary keys.

Revision ID: 0001
Revises:
Create Date: 2026-06-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fuentes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("url_base", sa.String(500), nullable=False),
        sa.Column("configuracion_yaml", sa.Text(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fuente_id", sa.Integer(), nullable=False),
        sa.Column("fecha_captura", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contenido_crudo", sa.Text(), nullable=False),
        sa.Column("screenshot_b64", sa.Text(), nullable=True),
        sa.Column("hash_contenido", sa.String(64), nullable=False),
        sa.Column("estado_ejecucion", sa.String(50), nullable=False),
        sa.Column("metadatos", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["fuente_id"], ["fuentes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fuente_id", sa.Integer(), nullable=True),
        sa.Column("nivel", sa.String(20), nullable=False),
        sa.Column("modulo", sa.String(50), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("detalles", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fuente_id"], ["fuentes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "convocatorias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fuente_id", sa.Integer(), nullable=False),
        sa.Column("identificador_externo", sa.String(255), nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("url_detalle", sa.String(500), nullable=True),
        sa.Column("fecha_apertura", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_cierre", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monto", sa.Float(), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("estado", sa.String(100), nullable=False),
        sa.Column("metadatos", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fuente_id"], ["fuentes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "historial_cambios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("convocatoria_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("fecha_deteccion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("es_apertura", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("delta", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("es_relevante", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["convocatoria_id"], ["convocatorias.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notificaciones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("historial_cambios_id", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(50), nullable=False),
        sa.Column("destinatario", sa.String(255), nullable=False),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(50), nullable=False),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["historial_cambios_id"], ["historial_cambios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "config_notificaciones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("configuracion", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "suscripciones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.String(100), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=True),
        sa.Column("regiones", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("token_confirmacion", sa.String(100), nullable=True),
        sa.Column("confirmado", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suscripciones_chat_id", "suscripciones", ["chat_id"])


def downgrade() -> None:
    op.drop_table("suscripciones")
    op.drop_table("config_notificaciones")
    op.drop_table("notificaciones")
    op.drop_table("historial_cambios")
    op.drop_table("convocatorias")
    op.drop_table("audit_logs")
    op.drop_table("snapshots")
    op.drop_table("fuentes")
