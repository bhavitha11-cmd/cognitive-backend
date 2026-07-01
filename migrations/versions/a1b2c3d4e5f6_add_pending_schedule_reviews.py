"""add pending_schedule_reviews table

Revision ID: a1b2c3d4e5f6
Revises: fc4997eeec63
Create Date: 2026-06-29

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "cb9c86269157"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_schedule_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "holiday_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("holidays.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "review_status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        # Uniqueness: one review per (holiday, project) pair
        sa.UniqueConstraint("holiday_id", "project_id", name="uq_psr_holiday_project"),
        # Status domain check
        sa.CheckConstraint(
            "review_status IN ('PENDING', 'APPLIED', 'REJECTED')",
            name="ck_psr_review_status",
        ),
    )

    # Primary access path: fetch all PENDING reviews for a specific owner
    op.create_index(
        "ix_psr_manager_status",
        "pending_schedule_reviews",
        ["project_manager_id", "review_status"],
    )

    # Secondary: cancel all PENDING reviews for a holiday when it is deactivated
    op.create_index(
        "ix_psr_holiday_id",
        "pending_schedule_reviews",
        ["holiday_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_psr_holiday_id", table_name="pending_schedule_reviews")
    op.drop_index("ix_psr_manager_status", table_name="pending_schedule_reviews")
    op.drop_table("pending_schedule_reviews")
