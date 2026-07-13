from __future__ import annotations

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.feature import Feature
from app.models.module import Module
from app.models.department import Department
from app.core.permission_scope import PermissionScope
from app.services.auth_engine_service import AuthorizationEngine

# Compile override for JSONB in SQLite
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture(name="engine")
def fixture_engine():
    return create_engine("sqlite:///:memory:")


@pytest.fixture(name="db_session")
def fixture_db_session(engine):
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(name="auth_engine")
def fixture_auth_engine(db_session):
    return AuthorizationEngine(db_session)


def test_resolve_scope_integration(db_session: Session, auth_engine: AuthorizationEngine):
    # 1. Create Module
    module = Module(
        id=uuid.uuid4(),
        module_key="projects",
        module_name="Projects",
        is_active=True,
    )
    db_session.add(module)
    db_session.flush()

    # 2. Create Feature under the module
    feature = Feature(
        id=uuid.uuid4(),
        module_id=module.id,
        feature_key="projects",
        feature_name="Projects Module",
        is_active=True,
    )
    db_session.add(feature)

    # 3. Create Role
    role = Role(
        id=uuid.uuid4(),
        role_code="DEVELOPER",
        name="Developer",
        is_active=True,
        data_access_level="SELF",
    )
    db_session.add(role)
    db_session.flush()

    # 4. Create RolePermission mapping projects:view -> OWNED
    perm = RolePermission(
        id=uuid.uuid4(),
        role_id=role.id,
        feature_id=feature.id,
        view_scope=PermissionScope.OWNED.value,
        create_scope=PermissionScope.NONE.value,
        update_scope=PermissionScope.NONE.value,
        delete_scope=PermissionScope.NONE.value,
    )
    db_session.add(perm)

    # 5. Create Employee and map to Role
    employee = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-005",
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@cognitive.com",
        username="janedoe",
        password_hash="fake_hash",
        is_active=True,
        token_version=1,
    )
    db_session.add(employee)
    db_session.flush()

    emp_role = EmployeeRole(
        id=uuid.uuid4(),
        employee_id=employee.id,
        role_id=role.id,
        is_active=True,
    )
    db_session.add(emp_role)
    db_session.commit()

    # Test boolean permission check
    assert auth_engine.has_permission(employee.id, "projects", "view") is True
    assert auth_engine.has_permission(employee.id, "projects", "create") is False

    # Test record access with OWNED scope
    assert auth_engine.can_access_record(
        user_id=employee.id,
        feature_key="projects",
        action="view",
        record_owner_id=employee.id,
    ) is True

    assert auth_engine.can_access_record(
        user_id=employee.id,
        feature_key="projects",
        action="view",
        record_owner_id=uuid.uuid4(), # Different owner
    ) is False
