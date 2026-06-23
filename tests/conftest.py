from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.database.base import Base
from app.main import app


# ── Test UUIDs ─────────────────────────────────────────────────────────────────

TEST_USER_ID = UUID("11111111-1111-4111-8111-111111111111")
TEST_EMPLOYEE_ID = UUID("22222222-2222-4222-8222-222222222222")
TEST_TASK_ID = UUID("33333333-3333-4333-8333-333333333333")
TEST_PROJECT_ID = UUID("44444444-4444-4444-8444-444444444444")
TEST_OTHER_USER_ID = UUID("55555555-5555-4555-8555-555555555555")
TEST_TIME_ENTRY_ID = UUID("66666666-6666-4666-8666-666666666666")
TEST_SESSION_ID = UUID("77777777-7777-4777-8777-777777777777")
TEST_BREAK_ID = UUID("88888888-8888-4888-8888-888888888888")
TEST_REWORK_ID = UUID("99999999-9999-4999-8999-999999999999")


# ── Mock Factory Helpers ───────────────────────────────────────────────────────


def make_mock_employee(
    id: UUID = TEST_EMPLOYEE_ID,
    first_name: str = "Test",
    last_name: str = "User",
    employee_code: str = "EMP001",
    is_active: bool = True,
) -> MagicMock:
    emp = MagicMock()
    emp.id = id
    emp.first_name = first_name
    emp.last_name = last_name
    emp.employee_code = employee_code
    emp.is_active = is_active
    return emp


def make_mock_task(
    id: UUID = TEST_TASK_ID,
    task_code: str = "TASK-001",
    title: str = "Test Task",
    project_id: UUID = TEST_PROJECT_ID,
    is_active: bool = True,
    estimated_hours: float = 10.0,
    actual_hours: float = 0.0,
    department_category: str = "CAD",
    status: str = "NOT_STARTED",
    rework_count: int = 0,
    total_rework_hours: float = 0.0,
    original_estimated_hours: float | None = None,
    actual_start_date: date | None = None,
    progress: float = 0.0,
) -> MagicMock:
    task = MagicMock()
    task.id = id
    task.task_code = task_code
    task.title = title
    task.project_id = project_id
    task.is_active = is_active
    task.estimated_hours = estimated_hours
    task.actual_hours = actual_hours
    task.department_category = department_category
    task.status = status
    task.rework_count = rework_count
    task.total_rework_hours = total_rework_hours
    task.original_estimated_hours = original_estimated_hours
    task.actual_start_date = actual_start_date
    task.progress = progress
    return task


def make_mock_project(
    id: UUID = TEST_PROJECT_ID,
    name: str = "Test Project",
    project_code: str = "PROJ-001",
) -> MagicMock:
    proj = MagicMock()
    proj.id = id
    proj.name = name
    proj.project_code = project_code
    return proj


def make_mock_time_entry(
    id: UUID = TEST_TIME_ENTRY_ID,
    employee_id: UUID = TEST_EMPLOYEE_ID,
    task_id: UUID = TEST_TASK_ID,
    project_id: UUID = TEST_PROJECT_ID,
    date_val: date = date(2026, 6, 15),
    hours_spent: float = 4.0,
    description: str | None = None,
    entry_type: str = "REGULAR",
    is_billable: bool = True,
    status: str = "DRAFT",
    rejection_reason: str | None = None,
    employee: MagicMock | None = None,
    task: MagicMock | None = None,
    project: MagicMock | None = None,
) -> MagicMock:
    entry = MagicMock()
    entry.id = id
    entry.employee_id = employee_id
    entry.task_id = task_id
    entry.project_id = project_id
    entry.date = date_val
    entry.hours_spent = hours_spent
    entry.description = description
    entry.entry_type = entry_type
    entry.is_billable = is_billable
    entry.status = status
    entry.submitted_at = None
    entry.approved_by = None
    entry.approved_at = None
    entry.rejection_reason = rejection_reason
    entry.created_at = datetime.now(timezone.utc)
    entry.updated_at = datetime.now(timezone.utc)
    entry.employee = employee or make_mock_employee(id=employee_id)
    entry.task = task or make_mock_task(id=task_id)
    entry.project = project or make_mock_project(id=project_id)
    entry.approver = None
    # Support model_dump() for FastAPI serialization
    entry.model_dump.return_value = {
        "id": id,
        "employee_id": employee_id,
        "employee_name": f"{entry.employee.first_name} {entry.employee.last_name}",
        "employee_code": entry.employee.employee_code,
        "task_id": task_id,
        "task_code": entry.task.task_code if entry.task else None,
        "task_title": entry.task.title if entry.task else None,
        "project_id": project_id,
        "project_name": entry.project.name if entry.project else None,
        "date": date_val,
        "hours_spent": hours_spent,
        "description": description,
        "entry_type": entry_type,
        "is_billable": is_billable,
        "status": status,
        "submitted_at": None,
        "approved_by": None,
        "approved_at": None,
        "rejection_reason": rejection_reason,
        "created_at": entry.created_at.isoformat(),
    }
    return entry


# ── Session Mock ───────────────────────────────────────────────────────────────


def _auto_populate_model_defaults(obj):
    """When a model instance is added to the mock db, auto-set defaults
    that would normally be set by the DB (PK via default=, timestamps)."""
    from datetime import datetime, timezone
    import uuid

    if obj.id is None or (isinstance(obj.id, uuid.UUID) and obj.id.int == 0):
        obj.id = uuid.uuid4()
    created_at = getattr(obj, 'created_at', None)
    if created_at is None:
        obj.created_at = datetime.now(timezone.utc)
    updated_at = getattr(obj, 'updated_at', None)
    if updated_at is None:
        obj.updated_at = datetime.now(timezone.utc)
    if getattr(obj, 'duration_minutes', None) is None:
        obj.duration_minutes = 0
    if getattr(obj, 'hours_spent', None) is None:
        obj.hours_spent = 0.0


@pytest.fixture
def mock_db():
    """Provides a fully mocked SQLAlchemy Session."""
    db = MagicMock()
    # Make scalar() and scalars() return sensible defaults
    db.scalar.return_value = None
    db.scalars.return_value = MagicMock()
    db.scalars.return_value.unique.return_value = MagicMock()
    db.scalars.return_value.unique.return_value.all.return_value = []
    db.scalars.return_value.first.return_value = None
    db.get.return_value = None

    def _add_side_effect(obj):
        _auto_populate_model_defaults(obj)

    db.add.side_effect = _add_side_effect
    return db


# ── Mock Factory Helpers for New Models ────────────────────────────────────────


def make_mock_task_work_session(
    id: UUID = TEST_SESSION_ID,
    employee_id: UUID = TEST_EMPLOYEE_ID,
    task_id: UUID = TEST_TASK_ID,
    project_id: UUID = TEST_PROJECT_ID,
    session_type: str = "REGULAR",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    duration_minutes: int = 0,
    status: str = "RUNNING",
    started_by: UUID | None = None,
    ended_by: UUID | None = None,
    pause_reason: str | None = None,
    remarks: str | None = None,
    task=None,
) -> MagicMock:
    now = datetime.now(timezone.utc)
    session = MagicMock()
    session.id = id
    session.employee_id = employee_id
    session.task_id = task_id
    session.project_id = project_id
    session.session_type = session_type
    session.start_time = start_time or now
    session.end_time = end_time
    session.duration_minutes = duration_minutes
    session.status = status
    session.started_by = started_by or employee_id
    session.ended_by = ended_by
    session.pause_reason = pause_reason
    session.remarks = remarks
    session.created_at = now
    session.updated_at = now
    session.task = task
    session.model_dump.return_value = {
        "id": id,
        "employee_id": employee_id,
        "task_id": task_id,
        "project_id": project_id,
        "session_type": session_type,
        "start_time": (start_time or now).isoformat(),
        "end_time": end_time.isoformat() if end_time else None,
        "duration_minutes": duration_minutes,
        "status": status,
        "started_by": started_by,
        "ended_by": ended_by,
        "pause_reason": pause_reason,
        "remarks": remarks,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    return session


def make_mock_employee_break(
    id: UUID = TEST_BREAK_ID,
    employee_id: UUID = TEST_EMPLOYEE_ID,
    break_start: datetime | None = None,
    break_end: datetime | None = None,
    duration_minutes: int = 0,
    date_val: date | None = None,
    remarks: str | None = None,
) -> MagicMock:
    now = datetime.now(timezone.utc)
    brk = MagicMock()
    brk.id = id
    brk.employee_id = employee_id
    brk.break_start = break_start or now
    brk.break_end = break_end
    brk.duration_minutes = duration_minutes
    brk.date = date_val or now.date()
    brk.remarks = remarks
    brk.created_at = now
    brk.model_dump.return_value = {
        "id": id,
        "employee_id": employee_id,
        "break_start": (break_start or now).isoformat(),
        "break_end": break_end.isoformat() if break_end else None,
        "duration_minutes": duration_minutes,
        "date": str(brk.date),
        "remarks": remarks,
        "created_at": now.isoformat(),
    }
    return brk


def make_mock_task_rework(
    id: UUID = TEST_REWORK_ID,
    task_id: UUID = TEST_TASK_ID,
    rework_number: int = 1,
    opened_by: UUID | None = None,
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
    reason: str | None = None,
    hours_spent: float = 0.0,
) -> MagicMock:
    now = datetime.now(timezone.utc)
    rw = MagicMock()
    rw.id = id
    rw.task_id = task_id
    rw.rework_number = rework_number
    rw.opened_by = opened_by or TEST_EMPLOYEE_ID
    rw.opened_at = opened_at or now
    rw.closed_at = closed_at
    rw.reason = reason
    rw.hours_spent = hours_spent
    rw.created_at = now
    rw.model_dump.return_value = {
        "id": id,
        "task_id": task_id,
        "rework_number": rework_number,
        "opened_by": opened_by,
        "opened_at": (opened_at or now).isoformat(),
        "closed_at": closed_at.isoformat() if closed_at else None,
        "reason": reason,
        "hours_spent": hours_spent,
        "created_at": now.isoformat(),
    }
    return rw


def make_mock_task_assignment(
    id: UUID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    task_id: UUID = TEST_TASK_ID,
    employee_id: UUID = TEST_EMPLOYEE_ID,
    status: str = "ASSIGNED",
) -> MagicMock:
    ta = MagicMock()
    ta.id = id
    ta.task_id = task_id
    ta.employee_id = employee_id
    ta.status = status
    ta.assigned_by = TEST_EMPLOYEE_ID
    ta.assigned_hours = 10.0
    ta.planned_start_date = None
    ta.planned_end_date = None
    ta.actual_start_date = None
    ta.actual_end_date = None
    ta.notes = None
    ta.assigned_at = datetime.now(timezone.utc)
    ta.completed_at = None
    return ta


def make_mock_attendance(
    id: UUID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    employee_id: UUID = TEST_EMPLOYEE_ID,
    date_val: date | None = None,
    clock_in: datetime | None = None,
    clock_out: datetime | None = None,
    status: str = "PRESENT",
) -> MagicMock:
    now = datetime.now(timezone.utc)
    att = MagicMock()
    att.id = id
    att.employee_id = employee_id
    att.date = date_val or now.date()
    att.clock_in = clock_in or now
    att.clock_out = clock_out
    att.status = status
    att.total_hours = 0.0
    att.is_late = False
    att.late_by_minutes = 0
    att.overtime_hours = 0.0
    att.notes = None
    att.created_at = now
    return att


# ── Service Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def time_entry_service(mock_db):
    """Returns a TimeEntryService instance with a mock DB session."""
    from app.services.time_entry_service import TimeEntryService
    return TimeEntryService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)


@pytest.fixture
def work_session_service(mock_db):
    from app.services.work_session_service import WorkSessionService
    return WorkSessionService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)


@pytest.fixture
def break_service(mock_db):
    from app.services.break_service import BreakService
    return BreakService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)


@pytest.fixture
def rework_service(mock_db):
    from app.services.rework_service import ReworkService
    return ReworkService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)


# ── App / Client Fixtures for API Tests ────────────────────────────────────────


def _make_test_app() -> FastAPI:
    """Create the FastAPI app with overridden dependencies for testing."""
    from app.database.session import get_db
    from app.dependencies import get_current_user

    from app.models.employee import Employee
    from app.models.employee_role import EmployeeRole
    from app.models.role import Role
    from app.core.rbac import UserContext, DataAccessLevel

    # Create mock super-admin employee with roles
    mock_role = MagicMock(spec=Role)
    mock_role.role_code = "ADMIN"
    mock_role.name = "Administrator"
    mock_role.is_super_admin = True
    mock_role.data_access_level = "FULL"

    mock_emp_role = MagicMock(spec=EmployeeRole)
    mock_emp_role.is_active = True
    mock_emp_role.role = mock_role

    mock_employee = MagicMock(spec=Employee)
    mock_employee.id = TEST_EMPLOYEE_ID
    mock_employee.is_active = True
    mock_employee.employee_roles = [mock_emp_role]

    test_db = MagicMock()
    test_db.scalar.return_value = None
    test_db.scalars.return_value = MagicMock()
    test_db.scalars.return_value.unique.return_value = MagicMock()
    test_db.scalars.return_value.unique.return_value.all.return_value = []
    test_db.scalars.return_value.unique.return_value.first.return_value = mock_employee
    test_db.get.return_value = None

    async def _override_get_current_user() -> str:
        return str(TEST_EMPLOYEE_ID)

    def _override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    return app


@pytest.fixture
def test_app():
    return _make_test_app()


@pytest.fixture
async def async_client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    test_app.dependency_overrides.clear()
