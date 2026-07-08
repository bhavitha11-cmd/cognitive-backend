import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy import update
from app.models.role import Role
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.scope_of_work import ScopeOfWork
from app.schemas.task_template import TaskTemplateCreate
from app.core.security import get_password_hash
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")


def seed_default_admin(db: Session):
    # ── 1. Ensure ADMIN role exists ────────────────────────────────────────────
    admin_role_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    admin_role = db.get(Role, admin_role_id)
    if not admin_role:
        admin_role = db.scalar(select(Role).where(Role.role_code == "ADMIN"))

    if not admin_role:
        admin_role = Role(
            id=admin_role_id,
            role_code="ADMIN",
            name="Administrator",
            description="System administrator with full access to all modules.",
            parent_role_id=None,
            hierarchy_level=1,
            is_system_role=True,
            is_super_admin=True,
            is_active=True,
        )
        db.add(admin_role)
        db.commit()
        db.refresh(admin_role)
        logger.info(f"[Seed] Created default admin role: {admin_role.name}")
    else:
        # Ensure super-admin flag is set
        if not getattr(admin_role, "is_super_admin", False):
            admin_role.is_super_admin = True
            admin_role.parent_role_id = None
            admin_role.hierarchy_level = 1
            db.add(admin_role)
            db.commit()

    # ── 2. Ensure admin employee exists ────────────────────────────────────────
    admin_emp_id = uuid.UUID("99999999-9999-9999-9999-999999999999")
    admin_emp = db.get(Employee, admin_emp_id)
    if not admin_emp:
        admin_emp = db.scalar(select(Employee).where(Employee.username == "admin"))

    if not admin_emp:
        admin_password = settings.DEFAULT_ADMIN_PASSWORD
        if not admin_password:
            raise ValueError(
                "DEFAULT_ADMIN_PASSWORD is not set in .env. "
                "Add it before starting the server."
            )
        admin_emp = Employee(
            id=admin_emp_id,
            employee_code="EMP-001",
            first_name="Admin",
            last_name="User",
            email="admin@cognitive.com",
            username="admin",
            password_hash=get_password_hash(admin_password),
            account_status="ACTIVE",
            is_active=True,
            gender="MALE",
            display_name="Admin User",
        )
        db.add(admin_emp)
        db.commit()
        db.refresh(admin_emp)
        logger.info(f"[Seed] Created default admin employee: {admin_emp.username}")

    # ── 3. Ensure admin employee has ADMIN role ────────────────────────────────
    emp_role = db.scalar(
        select(EmployeeRole).where(
            EmployeeRole.employee_id == admin_emp.id,
            EmployeeRole.role_id == admin_role.id,
        )
    )
    if not emp_role:
        emp_role = EmployeeRole(
            id=uuid.uuid4(),
            employee_id=admin_emp.id,
            role_id=admin_role.id,
            is_active=True,
        )
        db.add(emp_role)
        db.commit()
        logger.info("[Seed] Assigned ADMIN role to default admin employee")


def seed_scope_of_work(db: Session):
    SCOPE_OF_WORK_ENTRIES = [
        # CAD
        ("3D-MDL",          "3D Model",                                    "CAD"),
        ("3D-MDL-VAL",      "3D Model Validation",                         "CAD"),
        ("3D-MDL-CHG",      "3D Model Changes",                            "CAD"),
        ("1-1-DRG",         "1:1 Drawing",                                 "CAD"),
        ("1-1-DRG-VAL",     "1:1 Drawing Validation",                      "CAD"),
        ("STG-MDL",         "Stage Model",                                 "CAD"),
        ("STG-MDL-VAL",     "Stage Model Validation",                      "CAD"),
        ("STG-DRG",         "Stage Drawing",                               "CAD"),
        ("STG-DRG-VAL",     "Stage Drawing Validation",                    "CAD"),
        ("MOS",             "MOS",                                         "CAD"),
        ("MOS-VAL",         "MOS Validation",                              "CAD"),
        ("FIX-CNCPT",       "Fixture Concept Model",                       "CAD"),
        ("FIX-DTL",         "Fixture Detailing",                           "CAD"),
        ("FIX-VAL",         "Fixture Model and Detailing Validation",      "CAD"),
        ("MBD-CAP",         "MBD Capture",                                 "CAD"),
        ("MBD-VAL",         "MBD Capture Validation",                      "CAD"),
        ("BUBBLING",        "Bubbling",                                    "CAD"),
        ("LAI-RPT",         "LAI Report",                                  "CAD"),
        ("LAI-RPT-VAL",     "LAI Report Validation",                       "CAD"),
        ("MFG-ENGG",        "Manufacturing Engineering",                   "CAD"),
        # GEN (mixed in with CAD block per spec)
        ("CONTRACT-REV",    "Contract Review",                             "GEN"),
        ("BOM-CAP",         "BOM Capture",                                 "GEN"),
        # CAM
        ("CNC-PROG",        "CNC Programming",                             "CAM"),
        ("CNC-PROG-VAL",    "CNC Programming Validation",                  "CAM"),
        ("FIX-PROG",        "Fixture Programming",                         "CAM"),
        ("FIX-PROG-VAL",    "Fixture Programming Validation",              "CAM"),
        ("TOOL-LIST",       "Tool List",                                   "CAM"),
        ("TOOL-LIST-VAL",   "Tool List Validation",                        "CAM"),
        ("SETUP-SHEET",     "Setup Sheet Preparation",                     "CAM"),
        ("SETUP-SHEET-VAL", "Setup Sheet Validation",                      "CAM"),
        ("SIMULATION",      "Simulation",                                  "CAM"),
        ("SHP-FLR-SUPT",    "Shop Floor Support",                          "CAM"),
        # GEN
        ("ESTIMATION",      "Estimation",                                  "GEN"),
        ("PROC-PLAN",       "Process Planning",                            "GEN"),
        ("RFQ-INT",         "RFQ Internal",                                "GEN"),
        ("INTERNAL",        "Internal Work",                               "GEN"),
        ("MISC",            "Miscellaneous",                               "GEN"),
        # SALES
        ("QUOTE-PREP",      "Quote Preparation",                           "SALES"),
        ("INVOICE-PREP",    "Invoice Preparation",                         "SALES"),
        ("INVOICE-FUP",     "Invoice Follow Up",                           "SALES"),
        ("PAYMENT-FUP",     "Payment Follow Up",                           "SALES"),
        ("COM-MEET",        "Commercial Meeting",                          "SALES"),
        ("CUST-ENGAGE",     "Customer Engagement",                         "SALES"),
        # ADMIN
        ("HIRING",          "Hiring",                                      "ADMIN"),
        ("HR-ACT",          "HR Activities",                               "ADMIN"),
        ("LEAVE-MGT",       "Leave Management",                            "ADMIN"),
        # MKRT
        ("DIGITAL-MKT",     "Digital Marketing",                           "MKRT"),
        ("CONTENT-CREATE",  "Content Creation",                            "MKRT"),
        # SUPRT
        ("ONSITE-SUPT",     "Onsite Support",                              "SUPRT"),
    ]

    created = 0
    for code, name, department in SCOPE_OF_WORK_ENTRIES:
        exists = db.scalar(select(ScopeOfWork).where(ScopeOfWork.code == code))
        if not exists:
            entry = ScopeOfWork(
                id=uuid.uuid4(),
                code=code,
                name=name,
                department_category=department,
            )
            db.add(entry)
            created += 1

    if created:
        db.commit()
        logger.info(f"[Seed] Created {created} scope-of-work entries.")
    else:
        logger.info("[Seed] Scope-of-work entries already present, skipping.")


def seed_leave_types(db: Session):
    """Seed default leave types if none exist."""
    from app.models.leave_type import LeaveType

    LEAVE_TYPE_ENTRIES = [
        ("AL", "Annual Leave",    15.0, True,  True,  5.0,  "#3B82F6"),
        ("SL", "Sick Leave",       6.0, True,  False, 0.0,  "#EF4444"),
        ("CL", "Casual Leave",     6.0, True,  False, 0.0,  "#F59E0B"),
        ("EL", "Emergency Leave",  2.0, True,  False, 0.0,  "#8B5CF6"),
        ("UL", "Unpaid Leave",     0.0, False, False, 0.0,  "#6B7280"),
        ("ML", "Maternity Leave", 90.0, True,  False, 0.0,  "#EC4899"),
        ("PL", "Paternity Leave",  5.0, True,  False, 0.0,  "#06B6D4"),
    ]

    created = 0
    for code, name, days_per_year, is_paid, is_carry_forward, max_carry_forward, color in LEAVE_TYPE_ENTRIES:
        exists = db.scalar(select(LeaveType).where(LeaveType.code == code))
        if not exists:
            entry = LeaveType(
                id=uuid.uuid4(),
                code=code,
                name=name,
                days_per_year=days_per_year,
                is_paid=is_paid,
                is_carry_forward=is_carry_forward,
                max_carry_forward_days=max_carry_forward,
                color=color,
            )
            db.add(entry)
            created += 1

    if created:
        db.commit()
        logger.info(f"[Seed] Created {created} leave type entries.")
    else:
        logger.info("[Seed] Leave type entries already present, skipping.")


def seed_attendance_rule(db: Session):
    """Seed a single default attendance rule if none exist, updating with defaults if row exists."""
    from app.models.attendance_rule import AttendanceRule

    rule = db.scalar(select(AttendanceRule))
    if not rule:
        rule = AttendanceRule(
            id=uuid.uuid4(),
            office_start_time="08:00",
            office_end_time="20:00",
            half_day_hours=4.0,
            late_mark_after_minutes=15,
            work_days="MON,TUE,WED,THU,FRI",
            required_productive_hours=8.0,
            overtime_threshold_hours=9.0,
            max_break_minutes=60,
            min_break_minutes=0,
        )
        db.add(rule)
        db.commit()
        logger.info("[Seed] Created default attendance rule.")
    else:
        # Update existing rule with default values for new columns if they are not set (which is handled by server_default but good to ensure)
        dirty = False
        if rule.office_start_time == "09:00":
            rule.office_start_time = "08:00"
            dirty = True
        if rule.office_end_time == "18:00":
            rule.office_end_time = "20:00"
            dirty = True
        if getattr(rule, "required_productive_hours", None) is None:
            rule.required_productive_hours = 8.0
            dirty = True
        if getattr(rule, "overtime_threshold_hours", None) is None:
            rule.overtime_threshold_hours = 9.0
            dirty = True
        if getattr(rule, "max_break_minutes", None) is None:
            rule.max_break_minutes = 60
            dirty = True
        if getattr(rule, "min_break_minutes", None) is None:
            rule.min_break_minutes = 0
            dirty = True
        if dirty:
            db.add(rule)
            db.commit()
            logger.info("[Seed] Updated pre-existing default attendance rule fields.")


def seed_calendar_settings(db: Session):
    from app.models.calendar_settings import CalendarSettings

    exists = db.scalar(select(CalendarSettings))
    if not exists:
        settings = CalendarSettings(
            id=uuid.uuid4(),
            working_days="MON,TUE,WED,THU,FRI,SAT",
            weekend_days="SUN",
            office_start_time="09:00",
            office_end_time="18:00",
            default_daily_hours=8.0,
            working_hours_per_day=8.0,
            enable_birthdays=True,
            enable_company_events=True,
            enable_holidays=True,
            enable_task_events=True,
            enable_project_events=True,
            color_holiday="#EF4444",
            color_birthday="#EC4899",
            color_task="#3B82F6",
            color_project="#10B981",
            color_company_event="#8B5CF6",
        )
        db.add(settings)
        db.commit()
        logger.info("[Seed] Created default calendar settings.")


def seed_task_template_permissions(db: Session):
    from app.models.role_permission import RolePermission
    from app.models.role import Role
    from app.models.feature import Feature
    from app.core.permission_scope import PermissionScope

    admin_role = db.scalar(select(Role).where(Role.role_code == "ADMIN"))
    if not admin_role:
        logger.warning("[Seed] ADMIN role not found, skipping task template permissions.")
        return

    # Map TaskTemplate module to task_title_library feature
    feature = db.scalar(select(Feature).where(Feature.feature_key == "task_title_library"))
    if not feature:
        logger.warning("[Seed] Feature 'task_title_library' not found, skipping task template permissions.")
        return

    existing = db.scalar(
        select(RolePermission).where(
            RolePermission.role_id == admin_role.id,
            RolePermission.feature_id == feature.id,
        )
    )
    if not existing:
        perm = RolePermission(
            id=uuid.uuid4(),
            role_id=admin_role.id,
            feature_id=feature.id,
            module_name="TaskTemplate",
            view_scope=PermissionScope.ALL.value,
            create_scope=PermissionScope.ALL.value,
            update_scope=PermissionScope.ALL.value,
            delete_scope=PermissionScope.ALL.value,
        )
        db.add(perm)
        db.commit()
        logger.info("[Seed] Created TaskTemplate permission for ADMIN role.")
    else:
        logger.info("[Seed] TaskTemplate permission already present, skipping.")

    # Seed some default task titles
    from app.models.task_template import TaskTemplate
    existing_titles = {
        row[0].lower(): row[0]
        for row in db.execute(select(TaskTemplate.title)).all()
    }

    DEFAULT_TITLES = [
        "3D Modeling",
        "Assembly Modeling",
        "Drawing Creation",
        "GD&T",
        "Simulation",
        "Design Review",
        "Customer Review",
        "BOM Preparation",
        "Manufacturing Drawing",
        "Release Drawing",
        "Circuit Design",
        "PCB Layout",
        "Harness Design",
        "Requirement Analysis",
        "Concept Design",
        "Detail Engineering",
        "FEA Analysis",
        "CFD Analysis",
        "Material Selection",
        "Cost Estimation",
    ]

    from app.services.task_template_service import TaskTemplateService
    svc = TaskTemplateService(db)
    created = 0
    for title in DEFAULT_TITLES:
        if title.lower() not in existing_titles:
            svc.create(TaskTemplateCreate(title=title))
            created += 1

    if created:
        logger.info(f"[Seed] Created {created} default task templates.")
    else:
        logger.info("[Seed] Default task templates already present, skipping.")

    # Ensure we have a consistent admin for the audit fields if none set
    admin_emp = db.scalar(select(Employee).where(Employee.username == "admin"))
    if admin_emp:
        db.execute(
            update(TaskTemplate).where(TaskTemplate.created_by.is_(None)).values(created_by=admin_emp.id)
        )
        db.commit()


def seed_calendar_permissions(db: Session):
    from app.models.role_permission import RolePermission
    from app.models.role import Role
    from app.models.feature import Feature
    from app.core.permission_scope import PermissionScope

    # Define feature keys and their corresponding scopes
    # Format: (feature_key, legacy_module_name, view, create, update, delete)
    FEATURE_PERMISSIONS = [
        ("calendar", "Calendar", PermissionScope.ALL.value, PermissionScope.ALL.value, PermissionScope.ALL.value, PermissionScope.ALL.value),
        ("calendar_configuration", "CalendarSettings", PermissionScope.ALL.value, PermissionScope.ALL.value, PermissionScope.ALL.value, PermissionScope.ALL.value),
        ("my_dashboard", "Dashboard", PermissionScope.ALL.value, PermissionScope.NONE.value, PermissionScope.NONE.value, PermissionScope.NONE.value),
    ]

    created = 0
    for role_code in ["ADMIN", "HR"]:
        role = db.scalar(select(Role).where(Role.role_code == role_code))
        if not role:
            logger.warning(f"[Seed] Role {role_code} not found, skipping calendar permissions.")
            continue

        for feat_key, legacy_mod, view, create, update, delete in FEATURE_PERMISSIONS:
            feature = db.scalar(select(Feature).where(Feature.feature_key == feat_key))
            if not feature:
                logger.warning(f"[Seed] Feature '{feat_key}' not found, skipping permissions.")
                continue

            existing = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.feature_id == feature.id,
                )
            )
            if not existing:
                perm = RolePermission(
                    id=uuid.uuid4(),
                    role_id=role.id,
                    feature_id=feature.id,
                    module_name=legacy_mod,
                    view_scope=view,
                    create_scope=create,
                    update_scope=update,
                    delete_scope=delete,
                )
                db.add(perm)
                created += 1

    if created:
        db.commit()
        logger.info(f"[Seed] Created {created} calendar permissions.")
    else:
        logger.info("[Seed] Calendar permissions already present, skipping.")


def seed_idle_reasons(db: Session):
    from app.models.idle_reason_master import IdleReasonMaster
    
    DEFAULT_REASONS = [
        ("WAITING_REVIEW", "Waiting for Review", "Waiting for code or document review from colleagues/leads", 1, "#f59e0b"),
        ("MEETING", "Meeting", "Internal or project synchronization meeting", 2, "#3b82f6"),
        ("MACHINE_ISSUE", "Machine Issue", "Hardware, network, or electrical issues preventing engineering work", 3, "#ef4444"),
        ("MANAGER_DISCUSSION", "Manager Discussion", "Discussion or 1-on-1 with manager", 4, "#8b5cf6"),
        ("TRAINING", "Training", "Attending training sessions or tutorials", 5, "#10b981"),
        ("SYSTEM_ISSUE", "System Issue", "Software licenses, CAD/CAM tools, or VPN access issues", 6, "#ec4899"),
        ("CUSTOMER_CALL", "Customer Call", "Direct calls, presentations, or chats with clients", 7, "#06b6d4"),
        ("DOCUMENTATION", "Documentation", "Project documentation, timesheet management, or reports", 8, "#6b7280"),
        ("OTHER", "Other", "Any other reasons not covered by standard options", 9, "#9ca3af"),
    ]
    
    created = 0
    for code, name, desc, order, color in DEFAULT_REASONS:
        existing = db.scalar(select(IdleReasonMaster).where(IdleReasonMaster.code == code))
        if not existing:
            reason = IdleReasonMaster(
                id=uuid.uuid4(),
                code=code,
                name=name,
                description=desc,
                display_order=order,
                color=color,
                is_active=True
            )
            db.add(reason)
            created += 1
            
    if created:
        db.commit()
        logger.info(f"[Seed] Created {created} default idle reasons.")
    else:
        logger.info("[Seed] Default idle reasons already present, skipping.")
