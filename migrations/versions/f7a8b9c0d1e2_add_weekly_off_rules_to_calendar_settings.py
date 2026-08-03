"""add_weekly_off_rules_to_calendar_settings

Revision ID: f7a8b9c0d1e2
Revises: ca76efb10b27
Create Date: 2026-07-15 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'ca76efb10b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'calendar_settings',
        sa.Column('weekly_off_rules', sa.JSON(), nullable=True, default=None),
    )


def downgrade() -> None:
    op.drop_column('calendar_settings', 'weekly_off_rules')
