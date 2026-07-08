"""add_parts_and_tasks_part_id

Revision ID: 307fa2ef02ca
Revises: ee5f8c2225db
Create Date: 2026-07-08 15:20:18.373226

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '307fa2ef02ca'
down_revision: Union[str, Sequence[str], None] = 'ee5f8c2225db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
