import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import status
from app.dependencies import get_current_user
from app.database.session import get_db
from app.models.employee import Employee
from app.core.security import create_access_token, get_password_hash
from app.services.employee_service import EmployeeService
from app.schemas.employee import EmployeeUpdate

@pytest.fixture
def clean_auth_override(test_app):
    """Fixture to temporarily remove the get_current_user override to test real auth dependency logic."""
    override = test_app.dependency_overrides.get(get_current_user)
    if get_current_user in test_app.dependency_overrides:
        del test_app.dependency_overrides[get_current_user]
    yield
    if override:
        test_app.dependency_overrides[get_current_user] = override


@pytest.mark.asyncio
async def test_first_login_route_blocking(async_client, test_app, clean_auth_override):
    # 1. Setup mock database and mock employee who MUST change password using real Employee class instance
    emp_id = uuid4()
    mock_employee = Employee(
        id=emp_id,
        employee_code="EMP001",
        first_name="Test",
        last_name="User",
        email="test@user.com",
        username="testuser",
        password_hash=get_password_hash("OldPassword123!"),
        must_change_password=True,
        is_active=True,
        token_version=1,
        account_status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    # Set relationship defaults to avoid MagicMocks for relations
    mock_employee.employee_roles = []
    mock_employee.team_assignments = []

    mock_db = MagicMock()
    
    # Return mock_employee for employee query, and None for revoked tokens
    def mock_db_scalar(query):
        q_str = str(query).lower()
        if "revoked" in q_str:
            return None
        return mock_employee
    mock_db.scalar.side_effect = mock_db_scalar

    # Override get_db to return our mock_db
    test_app.dependency_overrides[get_db] = lambda: mock_db

    # Generate real access token for the mock employee
    token = create_access_token(subject=emp_id, token_version=1)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Verify that '/api/v1/auth/me' is ALLOWED
    # Mock _load_employee_with_roles and rbac context to let /me run
    mock_ctx = MagicMock()
    mock_ctx.data_access_level.value = "SELF"

    with patch("app.routers.auth._load_employee_with_roles", return_value=mock_employee), \
         patch("app.routers.auth._build_permissions", return_value=([], [], {})), \
         patch("app.core.rbac.get_user_context", return_value=mock_ctx):

        resp_me = await async_client.get("/api/v1/auth/me", headers=headers)
        assert resp_me.status_code == 200
        assert resp_me.json()["success"] is True
        assert resp_me.json()["data"]["must_change_password"] is True

    # 3. Verify that '/api/v1/employees' is BLOCKED (403 Password change required)
    resp_emp = await async_client.get("/api/v1/employees", headers=headers)
    assert resp_emp.status_code == status.HTTP_403_FORBIDDEN
    assert resp_emp.json()["detail"] == "Password change required"

    # Cleanup overrides
    del test_app.dependency_overrides[get_db]


@pytest.mark.asyncio
async def test_voluntary_password_change_refreshes_jwt(async_client, test_app, clean_auth_override):
    emp_id = uuid4()
    mock_employee = Employee(
        id=emp_id,
        employee_code="EMP001",
        first_name="Test",
        last_name="User",
        email="test@user.com",
        username="testuser",
        password_hash=get_password_hash("OldPassword123!"),
        must_change_password=True,
        is_active=True,
        token_version=1,
        account_status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    mock_employee.employee_roles = []
    mock_employee.team_assignments = []

    mock_db = MagicMock()
    
    def mock_db_scalar(query):
        q_str = str(query).lower()
        if "revoked" in q_str:
            return None
        return mock_employee
    mock_db.scalar.side_effect = mock_db_scalar
    mock_db.get.return_value = mock_employee

    test_app.dependency_overrides[get_db] = lambda: mock_db

    token = create_access_token(subject=emp_id, token_version=1)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "current_password": "OldPassword123!",
        "new_password": "NewPassword123!"
    }

    with patch("app.services.audit_service.AuditService.log") as mock_audit:
        resp = await async_client.post("/api/v1/auth/change-password", headers=headers, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "Password changed successfully"
        
        # Verify new JWT tokens are returned in the response data
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["token_type"] == "bearer"

        # Verify backend flags were updated correctly
        assert mock_employee.must_change_password is False
        assert mock_employee.password_changed_at is not None
        assert mock_employee.token_version == 2
        
        # Verify Audit Log entry was generated
        mock_audit.assert_any_call(mock_db, "employee", emp_id, "CHANGE_PASSWORD", performed_by=emp_id)

    del test_app.dependency_overrides[get_db]


def test_admin_password_reset_sets_must_change_password():
    # Test that EmployeeService.update resets must_change_password when password is in update body
    mock_db = MagicMock()
    emp_id = uuid4()
    
    mock_employee = Employee(
        id=emp_id,
        employee_code="EMP001",
        first_name="Test",
        last_name="User",
        email="test@user.com",
        username="testuser",
        password_hash=get_password_hash("OldPassword123!"),
        must_change_password=False,
        is_active=True,
        token_version=1,
        account_status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    mock_employee.employee_roles = []
    mock_employee.team_assignments = []

    # Mock repo and db
    service = EmployeeService(mock_db, current_user_id=uuid4())
    service.repo = MagicMock()
    service.repo.get_by_id.return_value = mock_employee
    service.repo.update.return_value = mock_employee

    # Update body containing new password
    update_data = EmployeeUpdate(password="NewTemporaryPass123!")

    with patch("app.services.audit_service.AuditService.log") as mock_audit:
        service.update(emp_id, update_data)

        # Retrieve arguments passed to repo.update
        called_args = service.repo.update.call_args[0][1]
        assert called_args["must_change_password"] is True
        assert called_args["password_changed_at"] is None
        assert "password_hash" in called_args

        # Verify audit logs include UPDATE and RESET_PASSWORD
        assert mock_audit.call_count == 2
        mock_audit.assert_any_call(mock_db, "employee", emp_id, "RESET_PASSWORD", performed_by=service.current_user_id, new_value={"employee_code": "EMP001"})
