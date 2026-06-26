"""add_missing_productivity_indexes

Revision ID: 9a11b64dfce5
Revises: fc4997eeec63
Create Date: 2026-06-26 20:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9a11b64dfce5'
down_revision: Union[str, Sequence[str], None] = 'fc4997eeec63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_idle_classifications_reason_id', 'idle_classifications', ['reason_id'], unique=False)
    op.create_index('ix_idle_reason_master_department_id', 'idle_reason_master', ['department_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_idle_reason_master_department_id', table_name='idle_reason_master')
    op.drop_index('ix_idle_classifications_reason_id', table_name='idle_classifications')
