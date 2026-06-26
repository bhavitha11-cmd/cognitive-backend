"""Create calendar_events table

Revision ID: 0003_calendar_events
Revises: 0002_calendar_holiday_settings
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_calendar_events"
down_revision: Union[str, Sequence[str], None] = "0002_calendar_holiday_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False, server_default="COMPANY_EVENT"),
        sa.Column("event_subtype", sa.String(50), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("is_all_day", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("text_color", sa.String(7), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_calendar_events_dates", "calendar_events", ["start_date", "end_date"])
    op.create_index("ix_calendar_events_type_active", "calendar_events", ["event_type", "is_active"])
    op.create_index("ix_calendar_events_reference", "calendar_events", ["reference_type", "reference_id"])


def downgrade() -> None:
    op.drop_table("calendar_events")
