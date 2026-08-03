"""
Database seeder for the Enterprise Authorization Platform.

This module runs on application startup and:
1. Seeds the Module & Feature registry tables with Cognitive ERP's features.
2. Migrates existing boolean-based role_permissions rows to the new scope model.

Idempotent: safe to run repeatedly — only inserts rows that don't exist yet.
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, inspect

from app.models.module import Module
from app.models.feature import Feature
from app.models.role_permission import RolePermission
from app.core.permission_scope import PermissionScope

logger = logging.getLogger(__name__)

# ── Module & Feature Definitions ────────────────────────────────────────────
# Each tuple: (module_key, module_name, icon, display_order, features_list)
# Features list: [(feature_key, feature_name, route, icon, display_order,
#                   menu_visible, permission_enabled, is_system)]

MODULE_REGISTRY: list[tuple] = [
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
        ("parts", "Parts", "/parts", None, 2, True, True, False),
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
    # ── Biometric Module (isolated, additive) ─────────────────────────────────
    ("biometric_settings", "Biometric Settings", "FingerprintOutlinedIcon", 11, [
        ("biometric_devices", "Devices", "/biometric/settings/devices", None, 1, True, True, False),
        ("biometric_connections", "Connection Profiles", "/biometric/settings/connections", None, 2, True, True, True),
        ("biometric_mapping", "Employee Mapping", "/biometric/settings/mapping", None, 3, True, True, False),
        ("biometric_sync_config", "Sync Configuration", "/biometric/settings/sync-config", None, 4, True, True, True),
        ("biometric_test", "Connection Test", "/biometric/settings/test", None, 5, True, True, True),
    ]),
    ("biometric_attendance", "Biometric Attendance", "AccessTimeOutlinedIcon", 12, [
        ("biometric_logs", "Biometric Logs", "/biometric/attendance/logs", None, 1, True, True, False),
        ("biometric_live", "Live Attendance", "/biometric/attendance/live", None, 2, True, True, False),
        ("biometric_sync_history", "Sync History", "/biometric/attendance/sync-history", None, 3, True, True, False),
        ("biometric_device_health", "Device Health", "/biometric/attendance/health", None, 4, True, True, True),
    ]),
]

# Mapping from old module_name strings to new feature_keys
# This is used to migrate existing boolean role_permissions rows.
OLD_MODULE_TO_FEATURE: dict[str, str] = {
    "HR": "employees",
    "Clients": "clients",
    "Finance": "settings",       # Finance mapped to settings for now
    "Projects": "projects",
    "Inventory": "settings",     # Inventory mapped to settings for now
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


def seed_modules_and_features(db: Session) -> None:
    """Seed the modules and features tables if they are empty or missing rows."""
    existing_modules = {
        m.module_key: m for m in db.scalars(select(Module)).all()
    }
    existing_feature_keys = set(
        db.scalars(select(Feature.feature_key)).all()
    )

    for mod_key, mod_name, mod_icon, mod_order, features_list in MODULE_REGISTRY:
        if mod_key not in existing_modules:
            module = Module(
                module_key=mod_key,
                module_name=mod_name,
                icon=mod_icon,
                display_order=mod_order,
            )
            db.add(module)
            db.flush()  # get module.id
            existing_modules[mod_key] = module
            logger.info(f"Created module '{mod_key}'")
        else:
            module = existing_modules[mod_key]

        features_created = 0
        for feat in features_list:
            feat_key, feat_name, route, icon, order, menu_vis, perm_en, is_sys = feat
            if feat_key in existing_feature_keys:
                continue

            feature = Feature(
                module_id=module.id,
                feature_key=feat_key,
                feature_name=feat_name,
                route=route,
                icon=icon,
                display_order=order,
                menu_visible=menu_vis,
                permission_enabled=perm_en,
                is_system=is_sys,
            )
            db.add(feature)
            existing_feature_keys.add(feat_key)
            features_created += 1

        if features_created > 0:
            logger.info(f"Seeded module '{mod_key}' with {features_created} new features.")

    db.commit()
    logger.info("Module & Feature seeding complete.")


def migrate_boolean_permissions(db: Session) -> None:
    """Migrate existing boolean-based role_permissions to scope-based permissions.

    For each existing row that has a module_name but no feature_id, look up the
    corresponding feature_key and set scope values based on the old boolean flags.
    """
    # Check if the role_permissions table has the old boolean columns
    inspector = inspect(db.bind)
    columns = {c["name"] for c in inspector.get_columns("role_permissions")}

    if "can_view" not in columns:
        logger.info("No legacy boolean columns found — skipping migration.")
        return

    # Find all permissions that have module_name but no feature_id
    legacy_perms = db.scalars(
        select(RolePermission).where(
            RolePermission.module_name.isnot(None),
            RolePermission.feature_id.is_(None),
        )
    ).all()

    if not legacy_perms:
        logger.info("No legacy permissions to migrate.")
        return

    # Build feature_key -> feature.id map
    features = db.scalars(select(Feature)).all()
    feature_map = {f.feature_key: f.id for f in features}

    migrated = 0
    for perm in legacy_perms:
        feature_key = OLD_MODULE_TO_FEATURE.get(perm.module_name)
        if not feature_key or feature_key not in feature_map:
            logger.warning(f"No feature mapping for module_name='{perm.module_name}' — skipping.")
            continue

        feature_id = feature_map[feature_key]

        # Check if this role already has a permission for this feature
        existing = db.scalar(
            select(RolePermission.id).where(
                RolePermission.role_id == perm.role_id,
                RolePermission.feature_id == feature_id,
            )
        )
        if existing:
            continue

        # Map booleans to scopes: True -> ALL, False -> NONE
        def _bool_to_scope(val: bool | None) -> str:
            return PermissionScope.ALL.value if val else PermissionScope.NONE.value

        perm.feature_id = feature_id
        perm.view_scope = _bool_to_scope(getattr(perm, '_can_view_legacy', None) or
                                          db.execute(
                                              select(RolePermission.__table__.c.can_view)
                                              .where(RolePermission.id == perm.id)
                                          ).scalar() if "can_view" in columns else False)
        perm.create_scope = _bool_to_scope(
            db.execute(
                select(RolePermission.__table__.c.can_create)
                .where(RolePermission.id == perm.id)
            ).scalar() if "can_create" in columns else False)
        perm.update_scope = _bool_to_scope(
            db.execute(
                select(RolePermission.__table__.c.can_edit)
                .where(RolePermission.id == perm.id)
            ).scalar() if "can_edit" in columns else False)
        perm.delete_scope = _bool_to_scope(
            db.execute(
                select(RolePermission.__table__.c.can_activate)
                .where(RolePermission.id == perm.id)
            ).scalar() if "can_activate" in columns else False)

        migrated += 1

    db.commit()
    logger.info(f"Migrated {migrated} legacy boolean permissions to scope-based model.")


def run_authorization_seeder(db: Session) -> None:
    """Main entry point called from app startup."""
    logger.info("Running Authorization Platform seeder...")
    seed_modules_and_features(db)
    migrate_boolean_permissions(db)
    logger.info("Authorization Platform seeder finished.")
