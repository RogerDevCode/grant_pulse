"""add_url_check_fields

Revision ID: 7efda2419024
Revises: 0338c8d1d224
Create Date: 2026-06-24 14:43:27.274157

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7efda2419024'
down_revision: Union[str, Sequence[str], None] = '0338c8d1d224'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('convocatorias', sa.Column('url_check_failures', sa.Integer(), server_default='0', nullable=False))
    op.add_column('convocatorias', sa.Column('ultimo_check_url', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('convocatorias', 'ultimo_check_url')
    op.drop_column('convocatorias', 'url_check_failures')
