"""add_modules_and_features_registry

Revision ID: ee5f8c2225db
Revises: a7c9d1e3f5b2
Create Date: 2026-07-08 14:13:46.429855

"""
from typing import Sequence, Union
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'ee5f8c2225db'
down_revision: Union[str, Sequence[str], None] = 'a7c9d1e3f5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Module & Feature Definitions
MODULE_REGISTRY = [
    ("dashboard", "Dashboard", "DashboardOutlinedIcon", 1, [
        ("private_dashboard", "Private Dashboard", "/dashboard/private", None, 1, True, True, False),
        ("advanced_dashboard", "Advanced Dashboard", "/dashboard/advanced", None, 2, True, True, False),
        ("executive_dashboard", "Executive Dashboard", "/dashboard/executive", None, 3, True, True, False),
        ("team_leader_dashboard", "Team Leader Dashboard", "/dashboard/team-leader", None, 4, True, True, False),
        ("my_dashboard", "My Dashboard", "/dashboard/employee", None, 5, True, True, False),
        ("employee_performance", "Employee Performance", "/dashboard/employee-performance", None, 6, True, True, False),
        ("employee_load_chart", "Employee Load Chart", "/dashboard/employee-load", None, 7, True, True, False),
    ]),
    ("clients", "Clients", "PeopleOutlinedIcon", 2, [
        ("clients", "Clients", "/clients", None, 1, True, True, False),
    ]),
    ("hr", "HR", "BadgeOutlinedIcon", 3, [
        ("employees", "Employees", "/hr/employees", None, 1, True, True, False),
        ("roles", "Roles", "/hr/roles", None, 2, True, True, True),
        ("departments", "Departments", "/hr/departments", None, 3, True, True, False),
        ("teams", "Teams", "/hr/teams", None, 4, True, True, False),
        ("org_chart", "Org Chart", "/hr/organization-chart", None, 5, True, True, False),
        ("offboarding", "Offboarding", "/hr/offboarding", None, 6, True, True, False),
        ("audit_logs", "Audit Logs", "/hr/audit-logs", None, 7, True, True, True),
        ("attendance_settings", "Attendance Settings", "/hr/attendance-settings", None, 8, True, True, False),
    ]),
    ("projects", "Projects", "FolderOutlinedIcon", 4, [
        ("projects", "Projects", "/projects", None, 1, True, True, False),
    ]),
    ("tasks", "Tasks", "AssignmentOutlinedIcon", 5, [
        ("tasks", "Tasks", "/tasks", None, 1, True, True, False),
    ]),
    ("timesheets", "Timesheets", "ScheduleOutlinedIcon", 6, [
        ("work_center", "Work Center", "/timesheets/active", None, 1, True, True, False),
        ("weekly_timesheet", "Weekly Timesheet", "/timesheets/weekly", None, 2, True, True, False),
        ("session_history", "Session History", "/timesheets", None, 3, True, True, False),
        ("attendance", "Attendance", "/timesheets/attendance", None, 4, True, True, False),
        ("my_leaves", "My Leaves", "/timesheets/leave", None, 5, True, True, False),
        ("leave_approval", "Leave Approval", "/timesheets/leave-approval", None, 6, True, True, False),
    ]),
    ("calendar", "Calendar", "CalendarTodayOutlinedIcon", 7, [
        ("calendar", "Calendar", "/calendar", None, 1, True, True, False),
    ]),
    ("reports", "Reports", "BarChartOutlinedIcon", 8, [
        ("reports", "Reports", "/reports", None, 1, True, True, False),
    ]),
    ("master_data", "Master Data", "LibraryBooksOutlinedIcon", 9, [
        ("task_title_library", "Task Title Library", "/master-data/task-templates", None, 1, True, True, False),
        ("calendar_configuration", "Calendar Configuration", "/master-data/calendar-config", None, 2, True, True, False),
    ]),
    ("settings", "Settings", "SettingsOutlinedIcon", 10, [
        ("settings", "Settings", "/settings", None, 1, True, True, True),
    ]),
]

OLD_MODULE_TO_FEATURE = {
    "HR": "employees",
    "Clients": "clients",
    "Finance": "settings",
    "Projects": "projects",
    "Inventory": "settings",
    "Settings": "settings",
    "Reports": "reports",
    "Timesheets": "work_center",
    "Tasks": "tasks",
    "Attendance": "attendance",
    "Leave": "my_leaves",
    "Analytics": "advanced_dashboard",
    "Dashboard": "my_dashboard",
    "TaskTemplate": "task_title_library",
}


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create modules registry table
    op.create_table('modules',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('module_key', sa.String(length=50), nullable=False),
        sa.Column('module_name', sa.String(length=100), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('icon', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_modules_module_key'), 'modules', ['module_key'], unique=True)

    # 2. Create features registry table
    op.create_table('features',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('module_id', sa.UUID(), nullable=False),
        sa.Column('feature_key', sa.String(length=50), nullable=False),
        sa.Column('feature_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('route', sa.String(length=200), nullable=True),
        sa.Column('icon', sa.String(length=100), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('menu_visible', sa.Boolean(), nullable=False, comment='Show this feature in the sidebar navigation'),
        sa.Column('permission_enabled', sa.Boolean(), nullable=False, comment='Include this feature in the permission matrix'),
        sa.Column('is_system', sa.Boolean(), nullable=False, comment='System features cannot be deactivated by admins'),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['module_id'], ['modules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_features_feature_key'), 'features', ['feature_key'], unique=True)
    op.create_index(op.f('ix_features_module_id'), 'features', ['module_id'], unique=False)

    # 3. Create role permission audits table
    op.create_table('role_permission_audits',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('role_id', sa.UUID(), nullable=False),
        sa.Column('feature_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False, comment='Permission action: view, create, update, delete'),
        sa.Column('old_scope', sa.String(length=50), nullable=False),
        sa.Column('new_scope', sa.String(length=50), nullable=False),
        sa.Column('changed_by', sa.UUID(), nullable=True),
        sa.Column('changed_on', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['feature_id'], ['features.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_role_permission_audits_feature_id'), 'role_permission_audits', ['feature_id'], unique=False)
    op.create_index(op.f('ix_role_permission_audits_role_id'), 'role_permission_audits', ['role_id'], unique=False)

    # 4. Seed Modules & Features into database so we have feature IDs for migration
    bind = op.get_bind()
    session = Session(bind=bind)

    feature_key_to_id = {}
    for mod_key, mod_name, mod_icon, mod_order, features_list in MODULE_REGISTRY:
        module_id = uuid.uuid4()
        session.execute(
            text(
                "INSERT INTO modules (id, module_key, module_name, display_order, icon, is_active, created_at) "
                "VALUES (:id, :module_key, :module_name, :display_order, :icon, true, now())"
            ),
            {"id": module_id, "module_key": mod_key, "module_name": mod_name, "display_order": mod_order, "icon": mod_icon}
        )
        for feat in features_list:
            feat_key, feat_name, route, icon, order, menu_vis, perm_en, is_sys = feat
            feat_id = uuid.uuid4()
            session.execute(
                text(
                    "INSERT INTO features (id, module_id, feature_key, feature_name, route, icon, display_order, "
                    "menu_visible, permission_enabled, is_system, is_active, created_at) "
                    "VALUES (:id, :module_id, :feature_key, :feature_name, :route, :icon, :display_order, "
                    ":menu_visible, :permission_enabled, :is_system, true, now())"
                ),
                {
                    "id": feat_id, "module_id": module_id, "feature_key": feat_key, "feature_name": feat_name,
                    "route": route, "icon": icon, "display_order": order, "menu_visible": menu_vis,
                    "permission_enabled": perm_en, "is_system": is_sys
                }
            )
            feature_key_to_id[feat_key] = feat_id
    session.commit()

    # 5. Add columns to role_permissions (temporarily nullable=True for feature_id)
    op.add_column('role_permissions', sa.Column('feature_id', sa.UUID(), nullable=True))
    op.add_column('role_permissions', sa.Column('view_scope', sa.String(length=50), server_default='NONE', nullable=False))
    op.add_column('role_permissions', sa.Column('create_scope', sa.String(length=50), server_default='NONE', nullable=False))
    op.add_column('role_permissions', sa.Column('update_scope', sa.String(length=50), server_default='NONE', nullable=False))
    op.add_column('role_permissions', sa.Column('delete_scope', sa.String(length=50), server_default='NONE', nullable=False))
    
    op.alter_column('role_permissions', 'module_name',
               existing_type=sa.VARCHAR(length=50),
               nullable=True)

    # 6. Migrate existing boolean role_permissions data to scope columns
    session = Session(bind=bind)
    existing_perms = session.execute(
        text("SELECT id, module_name, can_view, can_create, can_edit, can_activate FROM role_permissions")
    ).all()

    for perm in existing_perms:
        feature_key = OLD_MODULE_TO_FEATURE.get(perm.module_name)
        if not feature_key or feature_key not in feature_key_to_id:
            # If no mapping or feature not found, let's default to "settings" or fallback
            feature_key = "settings"
        
        feat_id = feature_key_to_id.get(feature_key)
        
        view_scope = "ALL" if perm.can_view else "NONE"
        create_scope = "ALL" if perm.can_create else "NONE"
        update_scope = "ALL" if perm.can_edit else "NONE"
        delete_scope = "ALL" if perm.can_activate else "NONE"

        session.execute(
            text(
                "UPDATE role_permissions "
                "SET feature_id = :feature_id, view_scope = :view_scope, create_scope = :create_scope, "
                "    update_scope = :update_scope, delete_scope = :delete_scope "
                "WHERE id = :id"
            ),
            {
                "id": perm.id, "feature_id": feat_id, "view_scope": view_scope, "create_scope": create_scope,
                "update_scope": update_scope, "delete_scope": delete_scope
            }
        )
    session.commit()

    # 7. Clean up any remaining rows that might not have feature_id populated (just in case)
    # Map them to the "settings" feature
    settings_id = feature_key_to_id.get("settings")
    if settings_id:
        session.execute(
            text("UPDATE role_permissions SET feature_id = :settings_id WHERE feature_id IS NULL"),
            {"settings_id": settings_id}
        )
        session.commit()

    # 8. Set feature_id column as NOT NULL now that it is fully populated
    op.alter_column('role_permissions', 'feature_id', nullable=False)

    # 9. Clean up constraints, index, unique
    op.drop_constraint('uq_role_module', 'role_permissions', type_='unique')
    op.create_index(op.f('ix_role_permissions_feature_id'), 'role_permissions', ['feature_id'], unique=False)
    op.create_unique_constraint('uq_role_feature', 'role_permissions', ['role_id', 'feature_id'])
    op.create_foreign_key(None, 'role_permissions', 'features', ['feature_id'], ['id'], ondelete='CASCADE')

    # 10. Drop old boolean columns
    op.drop_column('role_permissions', 'can_activate')
    op.drop_column('role_permissions', 'can_create')
    op.drop_column('role_permissions', 'can_edit')
    op.drop_column('role_permissions', 'can_view')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('role_permissions', sa.Column('can_view', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
    op.add_column('role_permissions', sa.Column('can_edit', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
    op.add_column('role_permissions', sa.Column('can_create', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
    op.add_column('role_permissions', sa.Column('can_activate', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
    
    # Re-migrate scopes to boolean if possible (ALL -> True, otherwise False)
    bind = op.get_bind()
    session = Session(bind=bind)
    perms = session.execute(
        text("SELECT id, view_scope, create_scope, update_scope, delete_scope FROM role_permissions")
    ).all()
    for perm in perms:
        can_view = perm.view_scope == "ALL"
        can_edit = perm.update_scope == "ALL"
        can_create = perm.create_scope == "ALL"
        can_activate = perm.delete_scope == "ALL"
        session.execute(
            text(
                "UPDATE role_permissions SET can_view = :can_view, can_edit = :can_edit, "
                "can_create = :can_create, can_activate = :can_activate WHERE id = :id"
            ),
            {"id": perm.id, "can_view": can_view, "can_edit": can_edit, "can_create": can_create, "can_activate": can_activate}
        )
    session.commit()

    op.drop_constraint(None, 'role_permissions', type_='foreignkey')
    op.drop_constraint('uq_role_feature', 'role_permissions', type_='unique')
    op.drop_index(op.f('ix_role_permissions_feature_id'), table_name='role_permissions')
    op.create_unique_constraint('uq_role_module', 'role_permissions', ['role_id', 'module_name'])
    op.alter_column('role_permissions', 'module_name',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)
    op.drop_column('role_permissions', 'delete_scope')
    op.drop_column('role_permissions', 'update_scope')
    op.drop_column('role_permissions', 'create_scope')
    op.drop_column('role_permissions', 'view_scope')
    op.drop_column('role_permissions', 'feature_id')
    op.drop_index(op.f('ix_role_permission_audits_role_id'), table_name='role_permission_audits')
    op.drop_index(op.f('ix_role_permission_audits_feature_id'), table_name='role_permission_audits')
    op.drop_table('role_permission_audits')
    op.drop_index(op.f('ix_features_module_id'), table_name='features')
    op.drop_index(op.f('ix_features_feature_key'), table_name='features')
    op.drop_table('features')
    op.drop_index(op.f('ix_modules_module_key'), table_name='modules')
    op.drop_table('modules')
