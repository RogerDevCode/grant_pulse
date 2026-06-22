"""add enriquecimiento columns

Revision ID: 0338c8d1d224
Revises: 05e8210785b9
Create Date: 2026-06-22 15:09:24.389944

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0338c8d1d224'
down_revision: Union[str, Sequence[str], None] = '05e8210785b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('convocatorias', sa.Column('estado_enriquecimiento', sa.String(length=20), server_default='PENDIENTE', nullable=False))
    op.add_column('convocatorias', sa.Column('detalles_llm', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('convocatorias', 'detalles_llm')
    op.drop_column('convocatorias', 'estado_enriquecimiento')
