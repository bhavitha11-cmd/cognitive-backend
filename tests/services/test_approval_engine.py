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
    # Direct database insertion to bypass level normalization and test gap validation
    invalid_step = ApprovalWorkflowStep(
        workflow_id=wf.id,
        requester_role_id=role_emp.id,
        level=2,
        approver_role_id=role_tl.id,
        resolution_scope="REPORTING_HIERARCHY"
    )
    db_session.add(invalid_step)
    db_session.commit()

    with pytest.raises(ValueError, match="Gaps found in levels"):
        service.activate_workflow(wf.id)

    # Clean up the invalid step
    db_session.delete(invalid_step)
    db_session.commit()

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


def test_leave_rejection_commits(db_session: Session, seed_data):
    emp = seed_data["employees"]["EMP"]
    tl = seed_data["employees"]["TL"]
    lt = seed_data["leave_type"]

    role_emp = seed_data["roles"]["EMP"]
    role_tl = seed_data["roles"]["TL"]

    approval_service = ApprovalService(db_session)
    leave_service = LeaveService(db_session, current_user_id=emp.id)

    # Create and Activate Workflow
    wf = approval_service.create_workflow(name="Leave Workflow", module_type="LEAVE")
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

    # Initialize leave balance
    leave_service.initialize_balances(emp.id, year=2026)

    # Apply for Leave
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
    ).all()
    assert len(instances) == 1

    # Action Level 1 (Team Lead Rejects)
    approval_service.submit_approval_action(
        employee_id=tl.id,
        instance_id=instances[0].id,
        action="REJECTED",
        comments="Rejected by TL"
    )

    # Assert that the changes were committed
    db_session.expire_all()
    req_obj = db_session.get(LeaveRequest, req_resp.id)
    assert req_obj.status == "REJECTED"
    assert req_obj.rejection_reason == "Rejected by TL"

    inst_obj = db_session.get(ApprovalInstance, instances[0].id)
    assert inst_obj.status == "REJECTED"


def test_cancel_approved_leave(db_session: Session, seed_data):
    from app.models.attendance import Attendance

    emp = seed_data["employees"]["EMP"]
    tl = seed_data["employees"]["TL"]
    lt = seed_data["leave_type"]

    role_emp = seed_data["roles"]["EMP"]
    role_tl = seed_data["roles"]["TL"]

    approval_service = ApprovalService(db_session)
    leave_service = LeaveService(db_session, current_user_id=emp.id)

    # Create and Activate Workflow
    wf = approval_service.create_workflow(name="Leave Workflow", module_type="LEAVE")
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

    # Initialize leave balance
    leave_service.initialize_balances(emp.id, year=2026)

    # Apply for Leave (July 17, 2026 is Friday) -> 1 working day (Friday July 17)
    from app.schemas.leave import LeaveRequestCreate
    leave_data = LeaveRequestCreate(
        leave_type_id=lt.id,
        from_date=date(2026, 7, 17),
        to_date=date(2026, 7, 17),
        reason="Vacation",
        document_url="http://example.com/doc.pdf"
    )
    req_resp = leave_service.apply_leave(leave_data, employee_id=emp.id)
    assert req_resp.status == "PENDING"
    assert req_resp.total_days == 1.0

    # Verify that ApprovalInstance steps were created
    instances = db_session.scalars(
        select(ApprovalInstance)
        .where(ApprovalInstance.target_id == req_resp.id)
    ).all()
    assert len(instances) == 1

    # Action Level 1 (Team Lead Approves)
    approval_service.submit_approval_action(
        employee_id=tl.id,
        instance_id=instances[0].id,
        action="APPROVED",
        comments="Approved by TL"
    )

    db_session.expire_all()
    req_obj = db_session.get(LeaveRequest, req_resp.id)
    assert req_obj.status == "APPROVED"

    # Verify that ON_LEAVE attendance was created for 2026-07-17
    att_records = db_session.scalars(
        select(Attendance).where(
            Attendance.employee_id == emp.id,
            Attendance.date == date(2026, 7, 17)
        )
    ).all()
    assert len(att_records) == 1
    assert att_records[0].status == "ON_LEAVE"

    # Verify that no ON_LEAVE attendance was created for 2026-07-18 or 2026-07-19 (weekends)
    att_sat = db_session.scalars(
        select(Attendance).where(
            Attendance.employee_id == emp.id,
            Attendance.date == date(2026, 7, 18)
        )
    ).all()
    assert len(att_sat) == 0

    # Verify used balance is 1.0
    from app.models.leave_balance import LeaveBalance
    balance = db_session.scalars(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == emp.id,
            LeaveBalance.leave_type_id == lt.id,
            LeaveBalance.year == 2026
        )
    ).first()
    assert balance.used == 1.0

    # Now Cancel the Approved Leave request
    leave_service.cancel_leave(req_resp.id)

    db_session.expire_all()
    req_obj = db_session.get(LeaveRequest, req_resp.id)
    assert req_obj.status == "CANCELLED"

    # Verify that the ON_LEAVE attendance record is deleted
    att_records_after = db_session.scalars(
        select(Attendance).where(
            Attendance.employee_id == emp.id,
            Attendance.date == date(2026, 7, 17)
        )
    ).all()
    assert len(att_records_after) == 0

    # Verify used balance is restored to 0.0
    balance_after = db_session.scalars(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == emp.id,
            LeaveBalance.leave_type_id == lt.id,
            LeaveBalance.year == 2026
        )
    ).first()
    assert balance_after.used == 0.0


def test_half_day_leave_lifecycle(db_session: Session, seed_data):
    from app.models.attendance import Attendance
    from app.models.leave_balance import LeaveBalance

    emp = seed_data["employees"]["EMP"]
    tl = seed_data["employees"]["TL"]
    lt = seed_data["leave_type"]

    role_emp = seed_data["roles"]["EMP"]
    role_tl = seed_data["roles"]["TL"]

    approval_service = ApprovalService(db_session)
    leave_service = LeaveService(db_session, current_user_id=emp.id)

    # Create and Activate Workflow
    wf = approval_service.create_workflow(name="Leave Workflow", module_type="LEAVE")
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

    # Initialize leave balance
    leave_service.initialize_balances(emp.id, year=2026)

    # 1. Apply for First Half Day Leave on Friday July 10, 2026
    from app.schemas.leave import LeaveRequestCreate
    leave_fh = LeaveRequestCreate(
        leave_type_id=lt.id,
        from_date=date(2026, 7, 10),
        to_date=date(2026, 7, 10),
        reason="Dentist appointment",
        is_half_day=True,
        half_day_session="FIRST_HALF"
    )
    req_fh = leave_service.apply_leave(leave_fh, employee_id=emp.id)
    assert req_fh.status == "PENDING"
    assert req_fh.total_days == 0.5

    # 2. Apply for Second Half Day Leave on same day (should succeed)
    leave_sh = LeaveRequestCreate(
        leave_type_id=lt.id,
        from_date=date(2026, 7, 10),
        to_date=date(2026, 7, 10),
        reason="Family errand",
        is_half_day=True,
        half_day_session="SECOND_HALF"
    )
    req_sh = leave_service.apply_leave(leave_sh, employee_id=emp.id)
    assert req_sh.status == "PENDING"
    assert req_sh.total_days == 0.5

    # 3. Try to apply for a Full Day Leave on the same day (should fail)
    leave_fd = LeaveRequestCreate(
        leave_type_id=lt.id,
        from_date=date(2026, 7, 10),
        to_date=date(2026, 7, 10),
        reason="Vacation overlap test",
        is_half_day=False
    )
    with pytest.raises(ValueError, match="overlaps with an existing PENDING request"):
        leave_service.apply_leave(leave_fd, employee_id=emp.id)

    # Verify that ApprovalInstance steps were created for both
    inst_fh = db_session.scalars(select(ApprovalInstance).where(ApprovalInstance.target_id == req_fh.id)).first()
    inst_sh = db_session.scalars(select(ApprovalInstance).where(ApprovalInstance.target_id == req_sh.id)).first()

    # 4. Action Level 1 for First Half (Approve)
    approval_service.submit_approval_action(
        employee_id=tl.id,
        instance_id=inst_fh.id,
        action="APPROVED",
        comments="Approved First Half"
    )
    db_session.expire_all()
    req_fh_obj = db_session.get(LeaveRequest, req_fh.id)
    assert req_fh_obj.status == "APPROVED"

    # Verify ON_LEAVE attendance was created with "First Half" in notes
    att_rec = db_session.scalars(select(Attendance).where(Attendance.employee_id == emp.id, Attendance.date == date(2026, 7, 10))).first()
    assert att_rec is not None
    assert att_rec.status == "ON_LEAVE"
    assert "First Half" in att_rec.notes

    # 5. Action Level 1 for Second Half (Approve)
    approval_service.submit_approval_action(
        employee_id=tl.id,
        instance_id=inst_sh.id,
        action="APPROVED",
        comments="Approved Second Half"
    )
    db_session.expire_all()
    req_sh_obj = db_session.get(LeaveRequest, req_sh.id)
    assert req_sh_obj.status == "APPROVED"

    # Verify both sessions are noted in the attendance record
    db_session.refresh(att_rec)
    assert "First Half" in att_rec.notes
    assert "Second Half" in att_rec.notes

    # Verify used balance is 1.0 (0.5 + 0.5)
    balance = db_session.scalars(select(LeaveBalance).where(LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type_id == lt.id, LeaveBalance.year == 2026)).first()
    assert balance.used == 1.0


def test_part_creation_without_department(db_session: Session, seed_data):
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService
    from app.schemas.project import ProjectCreate
    from app.schemas.task import TaskCreate
    from app.models.project import Project
    from app.models.task import Task
    from app.models.team import Team

    emp = seed_data["employees"]["EMP"]
    
    # Seed a Client
    from app.models.client import Client
    client = Client(id=uuid.uuid4(), name="Test Client", client_code="TC", is_active=True)
    db_session.add(client)
    db_session.flush()

    # 1. Create a Project (Part) without department_id
    project_service = ProjectService(db_session, current_user_id=emp.id)
    project_data = ProjectCreate(
        part_number="PART-NODEP-123",
        name="Package No Dep",
        part_name="Part No Dep",
        client_id=client.id,
        department_id=None,
        status="Yet To Start",
        priority="MEDIUM",
        estimated_hours=10.0
    )
    
    proj_resp = project_service.create(project_data)
    assert proj_resp.department_id is None
    
    # Verify it exists in DB with department_id as None
    db_proj = db_session.get(Project, proj_resp.id)
    assert db_proj is not None
    assert db_proj.department_id is None

    # 2. Get two teams belonging to different departments
    from app.models.department import Department
    dept1 = Department(id=uuid.uuid4(), name="CAD Dept", code="CAD", is_active=True)
    dept2 = Department(id=uuid.uuid4(), name="CAM Dept", code="CAM", is_active=True)
    db_session.add_all([dept1, dept2])
    db_session.flush()

    team_cad = Team(id=uuid.uuid4(), team_code="CAD", team_name="CAD Team", department_id=dept1.id, is_active=True)
    team_cam = Team(id=uuid.uuid4(), team_code="CAM", team_name="CAM Team", department_id=dept2.id, is_active=True)
    db_session.add_all([team_cad, team_cam])
    db_session.flush()

    # 3. Create a task under this project for CAD team
    task_service = TaskService(db_session, current_user_id=emp.id)
    task_data_cad = TaskCreate(
        project_id=proj_resp.id,
        task_code="T-001",
        title="CAD modeling task",
        team_id=team_cad.id,
        status="NOT_STARTED",
        priority="MEDIUM",
        estimated_hours=4.0
    )
    task_cad_resp = task_service.create(task_data_cad)
    assert task_cad_resp.team_id == team_cad.id

    # 4. Create a task under this same project for CAM team (should also succeed)
    task_data_cam = TaskCreate(
        project_id=proj_resp.id,
        task_code="T-002",
        title="CAM programming task",
        team_id=team_cam.id,
        status="NOT_STARTED",
        priority="MEDIUM",
        estimated_hours=6.0
    )
    task_cam_resp = task_service.create(task_data_cam)
    assert task_cam_resp.team_id == team_cam.id


def test_cannot_cancel_past_leave(db_session: Session, seed_data):
    from datetime import date, timedelta
    from app.schemas.leave import LeaveRequestCreate
    import pytest

    emp = seed_data["employees"]["EMP"]
    tl = seed_data["employees"]["TL"]
    lt = seed_data["leave_type"]
    role_emp = seed_data["roles"]["EMP"]
    role_tl = seed_data["roles"]["TL"]

    approval_service = ApprovalService(db_session)
    leave_service = LeaveService(db_session, current_user_id=emp.id)

    # Create and Activate Workflow
    wf = approval_service.create_workflow(name="Leave Workflow", module_type="LEAVE")
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

    # Initialize leave balance
    leave_service.initialize_balances(emp.id, year=2026)

    # Apply for Leave yesterday
    yesterday = date.today() - timedelta(days=1)
    leave_data = LeaveRequestCreate(
        leave_type_id=lt.id,
        from_date=yesterday,
        to_date=yesterday,
        reason="Sick",
        document_url=None
    )
    req_resp = leave_service.apply_leave(leave_data, employee_id=emp.id)
    assert req_resp.status == "PENDING"

    # Attempting to cancel should raise ValueError
    with pytest.raises(ValueError, match="Cannot cancel a leave request after its start date has passed"):
        leave_service.cancel_leave(req_resp.id)




