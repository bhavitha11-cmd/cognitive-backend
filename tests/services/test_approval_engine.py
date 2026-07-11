from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base
from app.models.approval import ApprovalInstance, ApprovalWorkflow, ApprovalWorkflowStep
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.role import Role
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.department import Department
from app.models.leave_type import LeaveType
from app.models.leave_request import LeaveRequest
from app.services.approval_service import ApprovalService
from app.services.leave_service import LeaveService


# Custom SQLite compiler override for Postgres-specific JSONB type used in audit logs
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture(name="engine")
def fixture_engine():
    # Use SQLite in-memory for fast integration testing
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


@pytest.fixture(name="seed_data")
def fixture_seed_data(db_session: Session):
    # 1. Create Roles
    role_emp = Role(id=uuid.uuid4(), role_code="EMPLOYEE", name="Employee", is_active=True, data_access_level="SELF")
    role_atl = Role(id=uuid.uuid4(), role_code="ATL", name="Associate Team Lead", is_active=True, data_access_level="TEAM")
    role_tl = Role(id=uuid.uuid4(), role_code="TL", name="Team Lead", is_active=True, data_access_level="TEAM")
    role_mgr = Role(id=uuid.uuid4(), role_code="MANAGER", name="Manager", is_active=True, data_access_level="MANAGED")
    role_ceo = Role(id=uuid.uuid4(), role_code="CEO", name="CEO", is_active=True, data_access_level="FULL")
    role_hr = Role(id=uuid.uuid4(), role_code="HR", name="HR Manager", is_active=True, data_access_level="FULL")
    db_session.add_all([role_emp, role_atl, role_tl, role_mgr, role_ceo, role_hr])
    db_session.flush()

    # 2. Create Departments
    dept_eng = Department(id=uuid.uuid4(), name="Engineering", code="ENG", is_active=True)
    dept_hr = Department(id=uuid.uuid4(), name="HR", code="HR", is_active=True)
    db_session.add_all([dept_eng, dept_hr])
    db_session.flush()

    # 3. Create Teams
    team_alpha = Team(id=uuid.uuid4(), team_name="Team Alpha", team_code="ALPHA", is_active=True, department_id=dept_eng.id)
    db_session.add(team_alpha)
    db_session.flush()

    # 4. Create Employees (Hierarchy: CEO -> Mgr -> TL -> ATL -> Emp)
    ceo = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-001",
        first_name="Alice",
        last_name="CEO",
        email="alice@company.com",
        username="alice",
        password_hash="hash",
        department_id=dept_eng.id,
        is_active=True
    )
    db_session.add(ceo)
    db_session.flush()

    mgr = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-002",
        first_name="Bob",
        last_name="Manager",
        email="bob@company.com",
        username="bob",
        password_hash="hash",
        reporting_manager_id=ceo.id,
        department_id=dept_eng.id,
        is_active=True
    )
    db_session.add(mgr)
    db_session.flush()

    tl = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-003",
        first_name="Charlie",
        last_name="TL",
        email="charlie@company.com",
        username="charlie",
        password_hash="hash",
        reporting_manager_id=mgr.id,
        department_id=dept_eng.id,
        is_active=True
    )
    db_session.add(tl)
    db_session.flush()

    atl = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-004",
        first_name="Dave",
        last_name="ATL",
        email="dave@company.com",
        username="dave",
        password_hash="hash",
        reporting_manager_id=tl.id,
        department_id=dept_eng.id,
        is_active=True
    )
    db_session.add(atl)
    db_session.flush()

    emp = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-005",
        first_name="Emma",
        last_name="Engineer",
        email="emma@company.com",
        username="emma",
        password_hash="hash",
        reporting_manager_id=atl.id,
        department_id=dept_eng.id,
        is_active=True
    )
    db_session.add(emp)
    db_session.flush()

    # Functional HR user
    hr_user = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-006",
        first_name="Helen",
        last_name="HR",
        email="helen@company.com",
        username="helen",
        password_hash="hash",
        department_id=dept_hr.id,
        is_active=True
    )
    db_session.add(hr_user)
    db_session.flush()

    # 5. Assign Roles
    db_session.add_all([
        EmployeeRole(employee_id=ceo.id, role_id=role_ceo.id, is_active=True),
        EmployeeRole(employee_id=mgr.id, role_id=role_mgr.id, is_active=True),
        EmployeeRole(employee_id=tl.id, role_id=role_tl.id, is_active=True),
        EmployeeRole(employee_id=atl.id, role_id=role_atl.id, is_active=True),
        EmployeeRole(employee_id=emp.id, role_id=role_emp.id, is_active=True),
        EmployeeRole(employee_id=hr_user.id, role_id=role_hr.id, is_active=True),
    ])
    db_session.flush()

    # 6. Assign Team Membership (Emma reports to ATL Dave, TL Charlie is Team Lead)
    db_session.add_all([
        TeamMember(team_id=team_alpha.id, employee_id=emp.id, role_in_team="MEMBER", is_primary_team=True),
        TeamMember(team_id=team_alpha.id, employee_id=tl.id, role_in_team="LEAD", is_primary_team=True),
    ])
    db_session.flush()

    # 7. Seed Leave Type
    lt_annual = LeaveType(id=uuid.uuid4(), code="AL", name="Annual Leave", days_per_year=15.0, is_active=True)
    db_session.add(lt_annual)
    db_session.commit()

    return {
        "roles": {"EMP": role_emp, "ATL": role_atl, "TL": role_tl, "MGR": role_mgr, "CEO": role_ceo, "HR": role_hr},
        "employees": {"CEO": ceo, "MGR": mgr, "TL": tl, "ATL": atl, "EMP": emp, "HR": hr_user},
        "leave_type": lt_annual,
    }


def test_workflow_activation_validation(db_session: Session, seed_data):
    role_emp = seed_data["roles"]["EMP"]
    role_tl = seed_data["roles"]["TL"]

    service = ApprovalService(db_session)

    # Create workflow
    wf = service.create_workflow(name="Leave Approval Flow", module_type="LEAVE")

    # Try activating empty workflow
    with pytest.raises(ValueError, match="no steps configured"):
        service.activate_workflow(wf.id)

    # Configure invalid steps (level gap: level 2 without level 1)
    steps_data = [
        {
            "requester_role_id": role_emp.id,
            "level": 2,
            "approver_role_id": role_tl.id,
            "resolution_scope": "REPORTING_HIERARCHY"
        }
    ]
    service.set_workflow_steps(wf.id, steps_data)

    with pytest.raises(ValueError, match="Gaps found in levels"):
        service.activate_workflow(wf.id)

    # Configure valid steps
    steps_data = [
        {
            "requester_role_id": role_emp.id,
            "level": 1,
            "approver_role_id": role_tl.id,
            "resolution_scope": "REPORTING_HIERARCHY"
        }
    ]
    service.set_workflow_steps(wf.id, steps_data)
    activated_wf = service.activate_workflow(wf.id)
    assert activated_wf.is_active is True


def test_approver_resolution_scopes(db_session: Session, seed_data):
    emp = seed_data["employees"]["EMP"]
    tl = seed_data["employees"]["TL"]
    mgr = seed_data["employees"]["MGR"]
    ceo = seed_data["employees"]["CEO"]
    hr = seed_data["employees"]["HR"]

    role_tl = seed_data["roles"]["TL"]
    role_mgr = seed_data["roles"]["MGR"]
    role_hr = seed_data["roles"]["HR"]

    service = ApprovalService(db_session)

    # 1. Test REPORTING_HIERARCHY
    step_rep = ApprovalWorkflowStep(
        workflow_id=uuid.uuid4(),
        requester_role_id=seed_data["roles"]["EMP"].id,
        level=1,
        approver_role_id=role_tl.id,
        resolution_scope="REPORTING_HIERARCHY"
    )
    resolved_rep = service.resolve_approver_for_step(emp.id, step_rep)
    # Emma -> Dave (ATL) -> Charlie (TL). The TL Charlie should be resolved.
    assert resolved_rep == tl.id

    step_rep_mgr = ApprovalWorkflowStep(
        workflow_id=uuid.uuid4(),
        requester_role_id=seed_data["roles"]["EMP"].id,
        level=1,
        approver_role_id=role_mgr.id,
        resolution_scope="REPORTING_HIERARCHY"
    )
    resolved_rep_mgr = service.resolve_approver_for_step(emp.id, step_rep_mgr)
    # Emma -> Dave -> Charlie -> Bob (Manager). Manager Bob should be resolved.
    assert resolved_rep_mgr == mgr.id

    # 2. Test TEAM_ASSIGNMENT
    step_team = ApprovalWorkflowStep(
        workflow_id=uuid.uuid4(),
        requester_role_id=seed_data["roles"]["EMP"].id,
        level=1,
        approver_role_id=role_tl.id,
        resolution_scope="TEAM_ASSIGNMENT"
    )
    resolved_team = service.resolve_approver_for_step(emp.id, step_team)
    # Emma is in Alpha team, Charlie is Lead. Charlie should be resolved.
    assert resolved_team == tl.id

    # 3. Test GLOBAL
    step_global = ApprovalWorkflowStep(
        workflow_id=uuid.uuid4(),
        requester_role_id=seed_data["roles"]["EMP"].id,
        level=1,
        approver_role_id=role_hr.id,
        resolution_scope="GLOBAL"
    )
    resolved_global = service.resolve_approver_for_step(emp.id, step_global)
    # Helen is global HR. Helen should be resolved.
    assert resolved_global == hr.id


def test_leave_approval_workflow_lifecycle(db_session: Session, seed_data):
    emp = seed_data["employees"]["EMP"]
    tl = seed_data["employees"]["TL"]
    hr = seed_data["employees"]["HR"]
    lt = seed_data["leave_type"]

    role_emp = seed_data["roles"]["EMP"]
    role_tl = seed_data["roles"]["TL"]
    role_hr = seed_data["roles"]["HR"]

    approval_service = ApprovalService(db_session)
    leave_service = LeaveService(db_session, current_user_id=emp.id)

    # 1. Create and Activate Workflow
    wf = approval_service.create_workflow(name="Leave Workflow", module_type="LEAVE")
    steps = [
        {
            "requester_role_id": role_emp.id,
            "level": 1,
            "approver_role_id": role_tl.id,
            "resolution_scope": "REPORTING_HIERARCHY"
        },
        {
            "requester_role_id": role_emp.id,
            "level": 2,
            "approver_role_id": role_hr.id,
            "resolution_scope": "GLOBAL"
        }
    ]
    approval_service.set_workflow_steps(wf.id, steps)
    approval_service.activate_workflow(wf.id)

    # Initialize leave balance
    leave_service.initialize_balances(emp.id, year=2026)

    # 2. Apply for Leave
    from app.schemas.leave import LeaveRequestCreate
    leave_data = LeaveRequestCreate(
        leave_type_id=lt.id,
        from_date=date(2026, 7, 10),
        to_date=date(2026, 7, 12),
        reason="Vacation",
        document_url="http://example.com/doc.pdf"
    )
    req_resp = leave_service.apply_leave(leave_data, employee_id=emp.id)
    assert req_resp.status == "PENDING"

    # Verify that ApprovalInstance steps were created
    instances = db_session.scalars(
        select(ApprovalInstance)
        .where(ApprovalInstance.target_id == req_resp.id)
        .order_by(ApprovalInstance.level)
    ).all()
    assert len(instances) == 2
    assert instances[0].level == 1
    assert instances[0].status == "PENDING"
    assert instances[0].assigned_approver_id == tl.id
    assert instances[1].level == 2
    assert instances[1].status == "DRAFT"

    # 3. Action Level 1 (Team Lead Approves)
    approval_service.submit_approval_action(
        employee_id=tl.id,
        instance_id=instances[0].id,
        action="APPROVED",
        comments="Approved by TL"
    )

    # Verify Level 1 is APPROVED, Level 2 is PENDING, overall LeaveRequest is still PENDING
    assert instances[0].status == "APPROVED"
    assert instances[1].status == "PENDING"

    req_obj = db_session.get(LeaveRequest, req_resp.id)
    assert req_obj.status == "PENDING"

    # 4. Action Level 2 (HR Approves)
    approval_service.submit_approval_action(
        employee_id=hr.id,
        instance_id=instances[1].id,
        action="APPROVED",
        comments="Approved by HR"
    )

    # Verify Level 2 is APPROVED, and overall LeaveRequest is now APPROVED
    assert instances[1].status == "APPROVED"
    assert req_obj.status == "APPROVED"
    assert req_obj.approved_by == hr.id
    assert req_obj.approved_at is not None


def test_leave_proration_based_on_joining_date(db_session: Session, seed_data):
    role_emp = seed_data["roles"]["EMP"]
    lt_annual = seed_data["leave_type"]  # 15 days/year

    # Create an employee who joined on October 15, 2026 (joining in current year)
    emp_oct = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-OCT",
        first_name="Octavia",
        last_name="October",
        email="octavia@company.com",
        username="octavia",
        password_hash="hash",
        date_of_joining=date(2026, 10, 15),
        is_active=True
    )
    db_session.add(emp_oct)
    db_session.flush()

    db_session.add(EmployeeRole(employee_id=emp_oct.id, role_id=role_emp.id, is_active=True))
    db_session.commit()

    leave_service = LeaveService(db_session)
    balances = leave_service.initialize_balances(emp_oct.id, year=2026)

    # 15 days/year * 3 months (Oct, Nov, Dec) / 12 = 3.75 days, rounded to nearest 0.5 = 4.0 days
    annual_balance = next(b for b in balances if b.leave_type_id == lt_annual.id)
    assert annual_balance.total_allowed == 4.0


def test_extra_leave_validation_rules(db_session: Session, seed_data):
    emp = seed_data["employees"]["EMP"]
    lt_annual = seed_data["leave_type"]  # Code "AL", which is not standard (CL/SL/Casual/Sick)

    # Create active workflow for Leave
    role_emp = seed_data["roles"]["EMP"]
    role_tl = seed_data["roles"]["TL"]
    approval_service = ApprovalService(db_session)
    wf = approval_service.create_workflow(name="Leave Flow", module_type="LEAVE")
    steps = [
        {
            "requester_role_id": role_emp.id,
            "level": 1,
            "approver_role_id": role_tl.id,
            "resolution_scope": "REPORTING_HIERARCHY"
        }
    ]
    approval_service.set_workflow_steps(wf.id, steps)
    approval_service.activate_workflow(wf.id)

    lt_annual.requires_document = True
    db_session.add(lt_annual)
    db_session.commit()

    leave_service = LeaveService(db_session, current_user_id=emp.id)
    leave_service.initialize_balances(emp.id, year=2026)

    from app.schemas.leave import LeaveRequestCreate

    # 1. Missing reason and document_url (should fail)
    leave_data_fail = LeaveRequestCreate(
        leave_type_id=lt_annual.id,
        from_date=date(2026, 7, 10),
        to_date=date(2026, 7, 12),
        reason=None,
        document_url=None
    )
    with pytest.raises(ValueError, match="Reason is mandatory for extra leaves"):
        leave_service.apply_leave(leave_data_fail, employee_id=emp.id)

    # 2. Reason provided, missing document_url (should fail)
    leave_data_fail2 = LeaveRequestCreate(
        leave_type_id=lt_annual.id,
        from_date=date(2026, 7, 10),
        to_date=date(2026, 7, 12),
        reason="Vacation justification",
        document_url=None
    )
    with pytest.raises(ValueError, match="Document upload is mandatory for extra leaves"):
        leave_service.apply_leave(leave_data_fail2, employee_id=emp.id)

    # 3. Both provided (should succeed)
    leave_data_success = LeaveRequestCreate(
        leave_type_id=lt_annual.id,
        from_date=date(2026, 7, 10),
        to_date=date(2026, 7, 12),
        reason="Vacation justification",
        document_url="/api/v1/leaves/document/test_doc.pdf"
    )
    resp = leave_service.apply_leave(leave_data_success, employee_id=emp.id)
    assert resp.status == "PENDING"
    assert resp.document_url == "/api/v1/leaves/document/test_doc.pdf"
