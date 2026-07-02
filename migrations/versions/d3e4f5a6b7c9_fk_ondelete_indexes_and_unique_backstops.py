"""FK ondelete fixes, drop duplicate departments FK, add indexes and partial unique backstops

Revision ID: d3e4f5a6b7c9
Revises: c2d3e4f5a6b8
Create Date: 2026-07-01

"""
from alembic import op
import sqlalchemy as sa


revision = "d3e4f5a6b7c9"
down_revision = "c2d3e4f5a6b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. task_transfer_history: from/to_employee_id CASCADE -> SET NULL ──────
    # These were created unnamed by op.create_table, so Postgres auto-named them
    # <table>_<column>_fkey. Drop and recreate with ondelete=SET NULL.
    op.drop_constraint(
        "task_transfer_history_from_employee_id_fkey",
        "task_transfer_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        "task_transfer_history_to_employee_id_fkey",
        "task_transfer_history",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "task_transfer_history_from_employee_id_fkey",
        "task_transfer_history",
        "employees",
        ["from_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "task_transfer_history_to_employee_id_fkey",
        "task_transfer_history",
        "employees",
        ["to_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── 2. task_risks.leave_request_id: NOT NULL + CASCADE -> NULLABLE + SET NULL
    op.alter_column(
        "task_risks",
        "leave_request_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.drop_constraint(
        "task_risks_leave_request_id_fkey",
        "task_risks",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "task_risks_leave_request_id_fkey",
        "task_risks",
        "leave_requests",
        ["leave_request_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── 3. Drop duplicate departments FK on department_head_id ─────────────────
    # Keep the explicitly named fk_departments_department_head_id (from initial
    # migration); drop the auto-named duplicate created later. Guarded so it is a
    # no-op if the duplicate is absent.
    op.execute(
        "ALTER TABLE departments "
        "DROP CONSTRAINT IF EXISTS departments_department_head_id_fkey"
    )

    # ── 4. Indexes on FK/lookup columns of history/event tables ────────────────
    op.create_index(
        "ix_employee_offboarding_events_employee_id",
        "employee_offboarding_events",
        ["employee_id"],
    )
    op.create_index(
        "ix_employee_offboarding_events_initiated_by",
        "employee_offboarding_events",
        ["initiated_by"],
    )
    op.create_index(
        "ix_project_manager_history_project_id",
        "project_manager_history",
        ["project_id"],
    )
    op.create_index(
        "ix_project_manager_history_employee_id",
        "project_manager_history",
        ["employee_id"],
    )
    op.create_index(
        "ix_department_head_history_department_id",
        "department_head_history",
        ["department_id"],
    )
    op.create_index(
        "ix_department_head_history_employee_id",
        "department_head_history",
        ["employee_id"],
    )

    # ── 5. Partial UNIQUE indexes to backstop check-then-act races ─────────────
    op.create_index(
        "uq_task_work_sessions_one_running_per_employee",
        "task_work_sessions",
        ["employee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_index(
        "uq_employee_breaks_one_open_per_employee",
        "employee_breaks",
        ["employee_id"],
        unique=True,
        postgresql_where=sa.text("break_end IS NULL"),
    )
    op.create_index(
        "uq_time_entries_employee_task_date",
        "time_entries",
        ["employee_id", "task_id", "date"],
        unique=True,
    )
    op.create_index(
        "uq_missed_clockout_pending_per_day",
        "missed_clockout_requests",
        ["employee_id", "attendance_date"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    # ── 6. Plain indexes on high-volume actor FK columns ───────────────────────
    op.create_index("ix_attendance_marked_by", "attendance", ["marked_by"])
    op.create_index("ix_time_entries_approved_by", "time_entries", ["approved_by"])
    op.create_index("ix_task_work_sessions_started_by", "task_work_sessions", ["started_by"])
    op.create_index("ix_task_work_sessions_ended_by", "task_work_sessions", ["ended_by"])
    op.create_index(
        "ix_missed_clockout_requests_reviewed_by",
        "missed_clockout_requests",
        ["reviewed_by"],
    )


def downgrade() -> None:
    # ── 6. Plain actor FK indexes ──────────────────────────────────────────────
    op.drop_index("ix_missed_clockout_requests_reviewed_by", table_name="missed_clockout_requests")
    op.drop_index("ix_task_work_sessions_ended_by", table_name="task_work_sessions")
    op.drop_index("ix_task_work_sessions_started_by", table_name="task_work_sessions")
    op.drop_index("ix_time_entries_approved_by", table_name="time_entries")
    op.drop_index("ix_attendance_marked_by", table_name="attendance")

    # ── 5. Partial unique indexes ──────────────────────────────────────────────
    op.drop_index("uq_missed_clockout_pending_per_day", table_name="missed_clockout_requests")
    op.drop_index("uq_time_entries_employee_task_date", table_name="time_entries")
    op.drop_index("uq_employee_breaks_one_open_per_employee", table_name="employee_breaks")
    op.drop_index("uq_task_work_sessions_one_running_per_employee", table_name="task_work_sessions")

    # ── 4. History/event lookup indexes ────────────────────────────────────────
    op.drop_index("ix_department_head_history_employee_id", table_name="department_head_history")
    op.drop_index("ix_department_head_history_department_id", table_name="department_head_history")
    op.drop_index("ix_project_manager_history_employee_id", table_name="project_manager_history")
    op.drop_index("ix_project_manager_history_project_id", table_name="project_manager_history")
    op.drop_index("ix_employee_offboarding_events_initiated_by", table_name="employee_offboarding_events")
    op.drop_index("ix_employee_offboarding_events_employee_id", table_name="employee_offboarding_events")

    # ── 3. Recreate the duplicate departments FK (auto-named) ──────────────────
    op.create_foreign_key(
        "departments_department_head_id_fkey",
        "departments",
        "employees",
        ["department_head_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── 2. task_risks.leave_request_id back to SET NULL FK but NOT NULL column ──
    op.drop_constraint("task_risks_leave_request_id_fkey", "task_risks", type_="foreignkey")
    op.create_foreign_key(
        "task_risks_leave_request_id_fkey",
        "task_risks",
        "leave_requests",
        ["leave_request_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "task_risks",
        "leave_request_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # ── 1. task_transfer_history FKs back to CASCADE ───────────────────────────
    op.drop_constraint("task_transfer_history_to_employee_id_fkey", "task_transfer_history", type_="foreignkey")
    op.drop_constraint("task_transfer_history_from_employee_id_fkey", "task_transfer_history", type_="foreignkey")
    op.create_foreign_key(
        "task_transfer_history_from_employee_id_fkey",
        "task_transfer_history",
        "employees",
        ["from_employee_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "task_transfer_history_to_employee_id_fkey",
        "task_transfer_history",
        "employees",
        ["to_employee_id"],
        ["id"],
        ondelete="CASCADE",
    )
