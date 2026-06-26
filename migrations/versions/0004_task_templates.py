"""Create task_templates table

Revision ID: 0004_task_templates
Revises: 0003_calendar_events
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_task_templates"
down_revision: Union[str, Sequence[str], None] = "0003_calendar_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_code", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_code", name="uq_task_template_code"),
        sa.ForeignKeyConstraint(["created_by"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_task_templates_is_active", "task_templates", ["is_active"])
    op.create_index("ix_task_templates_title", "task_templates", ["title"])


def downgrade() -> None:
    op.drop_table("task_templates")
