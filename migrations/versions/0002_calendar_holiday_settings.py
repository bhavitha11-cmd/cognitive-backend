"""Extend holidays table, create calendar_settings

Revision ID: 0002_calendar_holiday_settings
Revises: 0001_initial
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_calendar_holiday_settings"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Holidays: add columns ---
    op.add_column(
        "holidays",
        sa.Column("holiday_type", sa.String(50), nullable=False, server_default="PUBLIC"),
    )
    op.add_column(
        "holidays",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "holidays",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "holidays",
        sa.Column("created_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "holidays",
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "holidays",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "holidays",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Add UNIQUE(date) constraint (no existing constraint to drop — see rewrite note)
    op.create_unique_constraint("uq_holidays_date", "holidays", ["date"])

    # Foreign keys
    op.create_foreign_key(
        "fk_holidays_created_by",
        "holidays", "employees",
        ["created_by"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_holidays_updated_by",
        "holidays", "employees",
        ["updated_by"], ["id"],
        ondelete="SET NULL",
    )

    # --- Create calendar_settings table ---
    op.create_table(
        "calendar_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("working_days", sa.String(100), nullable=False, server_default="MON,TUE,WED,THU,FRI,SAT"),
        sa.Column("weekend_days", sa.String(100), nullable=False, server_default="SUN"),
        sa.Column("office_start_time", sa.String(5), nullable=False, server_default="09:00"),
        sa.Column("office_end_time", sa.String(5), nullable=False, server_default="18:00"),
        sa.Column("default_daily_hours", sa.Float(), nullable=False, server_default=sa.text("8.0")),
        sa.Column("working_hours_per_day", sa.Float(), nullable=False, server_default=sa.text("8.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Drop calendar_settings
    op.drop_table("calendar_settings")

    # Drop foreign keys first
    op.drop_constraint("fk_holidays_updated_by", "holidays", type_="foreignkey")
    op.drop_constraint("fk_holidays_created_by", "holidays", type_="foreignkey")

    # Drop the unique constraint we added
    op.drop_constraint("uq_holidays_date", "holidays", type_="unique")

    # Drop added columns
    op.drop_column("holidays", "updated_at")
    op.drop_column("holidays", "created_at")
    op.drop_column("holidays", "updated_by")
    op.drop_column("holidays", "created_by")
    op.drop_column("holidays", "is_active")
    op.drop_column("holidays", "description")
    op.drop_column("holidays", "holiday_type")
