import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.role import Role
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.core.security import get_password_hash

logger = logging.getLogger("uvicorn.error")

def seed_default_admin(db: Session):
    # Check if ADMIN role exists
    admin_role_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    admin_role = db.get(Role, admin_role_id)
    if not admin_role:
        # Check by name/code
        admin_role = db.scalar(select(Role).where(Role.role_code == "ADMIN"))
        
    if not admin_role:
        admin_role = Role(
            id=admin_role_id,
            role_code="ADMIN",
            name="Administrator",
            description="System administrator with full access to all system configurations and settings.",
            parent_role_id=None,
            hierarchy_level=1,
            is_system_role=True,
            is_active=True
        )
        db.add(admin_role)
        db.commit()
        db.refresh(admin_role)
        logger.info(f"[Database] Created default admin role: {admin_role.name}")
    else:
        # Ensure it has parent_role_id = None
        if admin_role.parent_role_id is not None:
            admin_role.parent_role_id = None
            admin_role.hierarchy_level = 1
            db.add(admin_role)
            db.commit()
            db.refresh(admin_role)
        
    # Check if admin employee exists
    admin_emp_id = uuid.UUID("99999999-9999-9999-9999-999999999999")
    admin_emp = db.get(Employee, admin_emp_id)
    if not admin_emp:
        admin_emp = db.scalar(select(Employee).where(Employee.username == "admin"))
        
    if not admin_emp:
        admin_emp = Employee(
            id=admin_emp_id,
            employee_code="EMP-001",
            first_name="Admin",
            last_name="User",
            email="admin@cognitive.com",
            username="admin",
            password_hash=get_password_hash("AdminPassword123!"),
            account_status="ACTIVE",
            is_active=True,
            gender="Male",
            display_name="Admin User"
        )
        db.add(admin_emp)
        db.commit()
        db.refresh(admin_emp)
        logger.info(f"[Database] Created default admin employee: {admin_emp.username}")
        
    # Check if admin employee has ADMIN role
    emp_role = db.scalar(
        select(EmployeeRole).where(
            EmployeeRole.employee_id == admin_emp.id,
            EmployeeRole.role_id == admin_role.id
        )
    )
    if not emp_role:
        emp_role = EmployeeRole(
            id=uuid.uuid4(),
            employee_id=admin_emp.id,
            role_id=admin_role.id,
            is_active=True
        )
        db.add(emp_role)
        db.commit()
        logger.info(f"[Database] Assigned ADMIN role to default admin employee")
