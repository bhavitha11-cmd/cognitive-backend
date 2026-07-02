"""add_additional_contacts

Revision ID: 4b6f14d77b4b
Revises: d3e4f5a6b7c9
Create Date: 2026-07-01 15:06:37.286106

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4b6f14d77b4b'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clients', sa.Column('additional_contacts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clients', 'additional_contacts')
