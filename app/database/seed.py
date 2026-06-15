import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.role import Role
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.scope_of_work import ScopeOfWork
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
    """Seed a single default attendance rule if none exist."""
    from app.models.attendance_rule import AttendanceRule

    exists = db.scalar(select(AttendanceRule))
    if not exists:
        rule = AttendanceRule(
            id=uuid.uuid4(),
            office_start_time="09:00",
            office_end_time="18:00",
            half_day_hours=4.0,
            late_mark_after_minutes=15,
            work_days="MON,TUE,WED,THU,FRI",
        )
        db.add(rule)
        db.commit()
        logger.info("[Seed] Created default attendance rule.")
