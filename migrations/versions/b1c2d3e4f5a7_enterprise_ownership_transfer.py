"""Enterprise Ownership Transfer Engine: new tables and employee offboarding columns

Revision ID: b1c2d3e4f5a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "b1c2d3e4f5a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add offboarding columns to employees ────────────────────────────
    op.add_column("employees", sa.Column("resignation_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("last_working_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("termination_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("offboard_reason", sa.String(500), nullable=True))
    op.add_column(
        "employees",
        sa.Column(
            "offboard_initiated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "employees",
        sa.Column(
            "successor_employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ── 2. employee_offboarding_events ────────────────────────────────────
    op.create_table(
        "employee_offboarding_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "initiated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("final_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("transfer_summary", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── 3. project_manager_history ────────────────────────────────────────
    op.create_table(
        "project_manager_history",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column(
            "changed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── 4. department_head_history ────────────────────────────────────────
    op.create_table(
        "department_head_history",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column(
            "changed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("department_head_history")
    op.drop_table("project_manager_history")
    op.drop_table("employee_offboarding_events")
    op.drop_column("employees", "successor_employee_id")
    op.drop_column("employees", "offboard_initiated_by")
    op.drop_column("employees", "offboard_reason")
    op.drop_column("employees", "termination_date")
    op.drop_column("employees", "last_working_date")
    op.drop_column("employees", "resignation_date")
