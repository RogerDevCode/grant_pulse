"""Cambiar region str a regiones JSON list[str]

Revision ID: 05e8210785b9
Revises: 0001
Create Date: 2026-06-21 19:33:36.024008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05e8210785b9'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('convocatorias', sa.Column('regiones', sa.JSON(), server_default='[]', nullable=False))
    op.execute("""
        UPDATE convocatorias 
        SET regiones = CASE 
            WHEN region IS NULL THEN '[]'::json 
            ELSE json_build_array(region) 
        END
    """)
    op.drop_column('convocatorias', 'region')


def downgrade() -> None:
    op.add_column('convocatorias', sa.Column('region', sa.String(length=100), nullable=True))
    op.execute("""
        UPDATE convocatorias 
        SET region = CASE 
            WHEN json_array_length(regiones) > 0 THEN regiones->>0 
            ELSE NULL 
        END
    """)
    op.drop_column('convocatorias', 'regiones')
