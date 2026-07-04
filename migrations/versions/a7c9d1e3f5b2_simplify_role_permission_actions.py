"""simplify_role_permission_actions

Revision ID: a7c9d1e3f5b2
Revises: 4b6f14d77b4b
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7c9d1e3f5b2'
down_revision: Union[str, Sequence[str], None] = '4b6f14d77b4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Collapse the RolePermission action set from 6 booleans down to 4:
    view / create / edit / activate. can_delete is renamed to can_activate
    (same grants, new meaning: toggles is_active, never a hard delete).
    can_approve/can_export are backfilled into can_edit/can_view so no role
    silently loses an existing grant, then dropped.
    """
    op.alter_column('role_permissions', 'can_delete', new_column_name='can_activate')

    op.execute("UPDATE role_permissions SET can_edit = true WHERE can_approve = true")
    op.execute("UPDATE role_permissions SET can_view = true WHERE can_export = true")

    op.drop_column('role_permissions', 'can_approve')
    op.drop_column('role_permissions', 'can_export')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('role_permissions', sa.Column('can_approve', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('role_permissions', sa.Column('can_export', sa.Boolean(), server_default=sa.false(), nullable=False))

    op.alter_column('role_permissions', 'can_activate', new_column_name='can_delete')
