"""merge_biometric_and_calendar_branches

Revision ID: 8fca154a9b6d
Revises: b1a2c3d4e5f6, f7a8b9c0d1e2
Create Date: 2026-07-31 13:51:10.322873

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fca154a9b6d'
down_revision: Union[str, Sequence[str], None] = ('b1a2c3d4e5f6', 'f7a8b9c0d1e2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
