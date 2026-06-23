"""initial_migration - create all tables from model metadata

Revision ID: 0001_initial
Revises: 
Create Date: 2026-06-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- departments ---
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("department_head_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_departments_department_head_id", "departments", ["department_head_id"])
    op.create_index("ix_departments_is_active", "departments", ["is_active"])

    # --- designations ---
    op.create_table(
        "designations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_designations_is_active", "designations", ["is_active"])
    op.create_foreign_key(None, "designations", "departments", ["department_id"], ["id"], ondelete="SET NULL")

    # --- employees ---
    op.create_table(
        "employees",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_code", sa.String(length=50), nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("official_email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("date_of_joining", sa.Date(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("designation_id", sa.Uuid(), nullable=True),
        sa.Column("reporting_manager_id", sa.Uuid(), nullable=True),
        sa.Column("employment_type", sa.String(length=50), nullable=False, server_default=sa.text("'PERMANENT'")),
        sa.Column("account_status", sa.String(length=50), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("password_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_code"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_employees_account_status", "employees", ["account_status"])
    op.create_index("ix_employees_is_active", "employees", ["is_active"])
    op.create_foreign_key(None, "employees", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "employees", "designations", ["designation_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "employees", "employees", ["reporting_manager_id"], ["id"], ondelete="SET NULL")

    # --- roles ---
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_access_level", sa.String(length=20), nullable=False, server_default=sa.text("'SELF'"),
                  comment="Row-level data visibility: FULL, MANAGED, TEAM, SELF"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_roles_is_active", "roles", ["is_active"])

    # --- role_permissions ---
    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "resource", "action"),
    )
    op.create_foreign_key(None, "role_permissions", "roles", ["role_id"], ["id"], ondelete="CASCADE")

    # --- employee_roles ---
    op.create_table(
        "employee_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(None, "employee_roles", "employees", ["employee_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "employee_roles", "roles", ["role_id"], ["id"], ondelete="CASCADE")

    # --- teams ---
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_code", sa.String(length=50), nullable=False),
        sa.Column("team_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("team_lead_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_code"),
        sa.UniqueConstraint("team_name"),
    )
    op.create_index("ix_teams_is_active", "teams", ["is_active"])
    op.create_foreign_key(None, "teams", "employees", ["team_lead_id"], ["id"], ondelete="SET NULL")

    # --- team_members ---
    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary_team", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "employee_id"),
    )
    op.create_foreign_key(None, "team_members", "teams", ["team_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "team_members", "employees", ["employee_id"], ["id"], ondelete="CASCADE")

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- revoked_tokens ---
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jti", sa.String(length=255), nullable=False),
        sa.Column("token_type", sa.String(length=50), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )

    # --- employee_role_history ---
    op.create_table(
        "employee_role_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("old_role_id", sa.Uuid(), nullable=True),
        sa.Column("new_role_id", sa.Uuid(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_erh_effective_dates", "employee_role_history", ["employee_id", "effective_from", "effective_to"])
    op.create_index("ix_erh_employee_id", "employee_role_history", ["employee_id"])
    op.create_foreign_key(None, "employee_role_history", "employees", ["employee_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "employee_role_history", "roles", ["new_role_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "employee_role_history", "roles", ["old_role_id"], ["id"], ondelete="SET NULL")

    # --- employee_reporting_history ---
    op.create_table(
        "employee_reporting_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("old_manager_id", sa.Uuid(), nullable=True),
        sa.Column("new_manager_id", sa.Uuid(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_emp_reporting_history_employee_changed_at", "employee_reporting_history", ["employee_id", "changed_at"])
    op.create_index("ix_emp_reporting_history_employee_id", "employee_reporting_history", ["employee_id"])
    op.create_index("ix_emp_reporting_history_new_manager_id", "employee_reporting_history", ["new_manager_id"])
    op.create_index("ix_emp_reporting_history_old_manager_id", "employee_reporting_history", ["old_manager_id"])
    op.create_foreign_key(None, "employee_reporting_history", "employees", ["employee_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "employee_reporting_history", "employees", ["old_manager_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "employee_reporting_history", "employees", ["new_manager_id"], ["id"], ondelete="SET NULL")

    # --- clients ---
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("client_code", sa.String(length=50), nullable=False),
        sa.Column("contact_person", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=20), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_code"),
    )

    # --- scope_of_work ---
    op.create_table(
        "scope_of_work",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope_code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("billing_type", sa.String(length=50), nullable=False, server_default=sa.text("'FIXED'")),
        sa.Column("hourly_rate", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("fixed_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'INR'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_code"),
    )

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column("scope_of_work_id", sa.Uuid(), nullable=True),
        sa.Column("project_manager_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'PLANNED'")),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default=sa.text("'MEDIUM'")),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("budget", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'INR'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_code"),
    )
    op.create_foreign_key(None, "projects", "clients", ["client_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "projects", "scope_of_work", ["scope_of_work_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "projects", "employees", ["project_manager_id"], ["id"], ondelete="SET NULL")

    # --- project_members ---
    op.create_table(
        "project_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("role_in_project", sa.String(length=100), nullable=True),
        sa.Column("allocation_percentage", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "employee_id"),
    )
    op.create_foreign_key(None, "project_members", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "project_members", "employees", ["employee_id"], ["id"], ondelete="CASCADE")

    # --- tasks ---
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'TO_DO'")),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default=sa.text("'MEDIUM'")),
        sa.Column("estimated_hours", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("original_estimated_hours", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("actual_hours", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("rework_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_rework_hours", sa.Numeric(precision=8, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "task_code"),
    )
    op.create_foreign_key(None, "tasks", "projects", ["project_id"], ["id"], ondelete="CASCADE")

    # --- task_assignments ---
    op.create_table(
        "task_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(None, "task_assignments", "tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "task_assignments", "employees", ["employee_id"], ["id"], ondelete="CASCADE")

    # --- task_dependencies ---
    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_task_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_type", sa.String(length=50), nullable=False, server_default=sa.text("'FINISH_TO_START'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "dependency_task_id"),
    )
    op.create_foreign_key(None, "task_dependencies", "tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "task_dependencies", "tasks", ["dependency_task_id"], ["id"], ondelete="CASCADE")

    # --- attendance_rules ---
    op.create_table(
        "attendance_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_name", sa.String(length=100), nullable=False),
        sa.Column("work_start_time", sa.Time(), nullable=False),
        sa.Column("work_end_time", sa.Time(), nullable=False),
        sa.Column("grace_period_minutes", sa.Integer(), nullable=False, server_default=sa.text("15")),
        sa.Column("half_day_minutes", sa.Integer(), nullable=True),
        sa.Column("full_day_hours", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("min_break_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("max_break_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- attendance ---
    op.create_table(
        "attendance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("clock_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clock_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ABSENT'")),
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("is_half_day", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "date"),
    )
    op.create_foreign_key(None, "attendance", "employees", ["employee_id"], ["id"], ondelete="CASCADE")

    # --- time_entries ---
    op.create_table(
        "time_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hours_spent", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("work_session_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(None, "time_entries", "employees", ["employee_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "time_entries", "tasks", ["task_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(None, "time_entries", "projects", ["project_id"], ["id"], ondelete="SET NULL")

    # --- leave_types ---
    op.create_table(
        "leave_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("leave_code", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("leave_code"),
    )

    # --- leave_balances ---
    op.create_table(
        "leave_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("total_days", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("used_days", sa.Numeric(precision=5, scale=1), nullable=False, server_default=sa.text("0")),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "leave_type_id", "year"),
    )
    op.create_foreign_key(None, "leave_balances", "employees", ["employee_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "leave_balances", "leave_types", ["leave_type_id"], ["id"], ondelete="CASCADE")

    # --- leave_requests ---
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(None, "leave_requests", "employees", ["employee_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "leave_requests", "leave_types", ["leave_type_id"], ["id"], ondelete="CASCADE")

    # --- employee_schedules ---
    op.create_table(
        "employee_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_working_day", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "day_of_week"),
    )
    op.create_foreign_key(None, "employee_schedules", "employees", ["employee_id"], ["id"], ondelete="CASCADE")

    # --- holidays ---
    op.create_table(
        "holidays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "name"),
    )

    # --- task_work_sessions ---
    op.create_table(
        "task_work_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'RUNNING'")),
        sa.Column("pause_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tws_employee_status", "task_work_sessions", ["employee_id", "status"])
    op.create_index("ix_tws_task_status", "task_work_sessions", ["task_id", "status"])
    op.create_foreign_key(None, "task_work_sessions", "tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "task_work_sessions", "employees", ["employee_id"], ["id"], ondelete="CASCADE")

    # --- employee_breaks ---
    op.create_table(
        "employee_breaks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("break_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("break_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("break_type", sa.String(length=50), nullable=True),
        sa.Column("duration_minutes", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(None, "employee_breaks", "employees", ["employee_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "employee_breaks", "task_work_sessions", ["session_id"], ["id"], ondelete="CASCADE")

    # --- task_rework_history ---
    op.create_table(
        "task_rework_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("rework_number", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rework_hours", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(None, "task_rework_history", "tasks", ["task_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    tables = [
        "task_rework_history",
        "employee_breaks",
        "task_work_sessions",
        "holidays",
        "employee_schedules",
        "leave_requests",
        "leave_balances",
        "leave_types",
        "time_entries",
        "attendance",
        "attendance_rules",
        "task_dependencies",
        "task_assignments",
        "tasks",
        "project_members",
        "projects",
        "scope_of_work",
        "clients",
        "employee_reporting_history",
        "employee_role_history",
        "revoked_tokens",
        "audit_logs",
        "team_members",
        "teams",
        "employee_roles",
        "role_permissions",
        "roles",
        "employees",
        "designations",
        "departments",
    ]
    for table_name in reversed(tables):
        op.drop_table(table_name)
