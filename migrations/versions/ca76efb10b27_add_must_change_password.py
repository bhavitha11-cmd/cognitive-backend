"""add_must_change_password

Revision ID: ca76efb10b27
Revises: 6ec0430a9503
Create Date: 2026-07-14 16:29:07.627164

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca76efb10b27'
down_revision: Union[str, Sequence[str], None] = '6ec0430a9503'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'employees',
        sa.Column('must_change_password', sa.Boolean(), server_default='true', nullable=False)
    )
    op.add_column(
        'employees',
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True)
    )
    # Mark all existing employees as requiring a password change
    op.execute("UPDATE employees SET must_change_password = TRUE")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('employees', 'password_changed_at')
    op.drop_column('employees', 'must_change_password')
