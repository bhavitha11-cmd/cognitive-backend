from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.leave_request import LeaveRequest
from app.models.task_continuity import TaskRisk, TaskPauseHistory, TaskTransferHistory, TaskDelegation, ManagerDecision
from app.schemas.task_continuity import ManagerDecisionCreate
from app.services.task_continuity_service import TaskContinuityService


@pytest.fixture
def db():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None
    mock_db.scalars.return_value = MagicMock()
    mock_db.scalars.return_value.all.return_value = []
    mock_db.scalars.return_value.first.return_value = None
    return mock_db


@pytest.fixture
def service(db):
    return TaskContinuityService(db, current_user_id=uuid.uuid4())


def test_detect_and_create_task_risks(db, service):
    employee_id = uuid.uuid4()
    leave = LeaveRequest(
        id=uuid.uuid4(),
        employee_id=employee_id,
        from_date=date(2026, 7, 5),
        to_date=date(2026, 7, 10),
        total_days=6,
        status="APPROVED",
    )

    task = Task(
        id=uuid.uuid4(),
        title="CAM Programming",
        task_code="TASK-001",
        estimated_hours=40.0,
        actual_hours=12.0,
        planned_start_date=date(2026, 7, 1),
        planned_end_date=date(2026, 7, 15),
        planned_delivery_date=date(2026, 7, 15),
        is_active=True,
        status="IN_PROGRESS",
    )

    assignment = TaskAssignment(
        id=uuid.uuid4(),
        task_id=task.id,
        employee_id=employee_id,
        planned_start_date=date(2026, 7, 1),
        planned_end_date=date(2026, 7, 15),
        status="ASSIGNED",
    )
    assignment.task = task

    db.scalars.return_value.all.return_value = [assignment]
    db.scalars.return_value.first.return_value = None  # No existing risk

    with patch("app.services.task_continuity_service.WorkingDayEngine.count_working_days", return_value=5) as mock_count:
        with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
            risks = service.detect_and_create_task_risks(employee_id, leave)
            
            assert len(risks) == 1
            assert risks[0].remaining_hours == 28.0
            assert risks[0].risk_level == "HIGH"
            assert risks[0].days_impacted == 5
            mock_count.assert_called_once()
            mock_audit.assert_called_once()


def test_resolve_task_risk_continue(db, service):
    risk_id = uuid.uuid4()
    manager_id = uuid.uuid4()

    task = Task(id=uuid.uuid4(), title="CAD Design", project_id=uuid.uuid4(), status="IN_PROGRESS")
    assignment = TaskAssignment(id=uuid.uuid4(), task_id=task.id, employee_id=uuid.uuid4(), status="ASSIGNED")
    risk = TaskRisk(
        id=risk_id,
        task_id=task.id,
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        remaining_hours=10.0,
        status="PENDING_MANAGER_ACTION",
    )
    risk.task = task
    risk.assignment = assignment
    risk.employee = MagicMock()

    db.get.side_effect = lambda model, id_: risk if model == TaskRisk else None
    service.repo.get_risk_by_id = MagicMock(return_value=risk)

    decision_data = ManagerDecisionCreate(decision="CONTINUE", reason="Keep assignment")

    with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
        with patch("app.services.task_continuity_service.ProjectMetricsService.recalculate") as mock_recalc:
            with patch("app.services.task_continuity_service.PlanningService.schedule_project") as mock_sched:
                decision = service.resolve_task_risk(risk_id, manager_id, decision_data)
                
                assert risk.status == "RESOLVED"
                assert decision.decision == "CONTINUE"
                mock_audit.assert_called_once()
                mock_recalc.assert_called_once()
                mock_sched.assert_called_once()


def test_resolve_task_risk_pause(db, service):
    risk_id = uuid.uuid4()
    manager_id = uuid.uuid4()

    task = Task(id=uuid.uuid4(), title="CAD Design", project_id=uuid.uuid4(), status="IN_PROGRESS")
    assignment = TaskAssignment(id=uuid.uuid4(), task_id=task.id, employee_id=uuid.uuid4(), status="ASSIGNED")
    risk = TaskRisk(
        id=risk_id,
        task_id=task.id,
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        remaining_hours=10.0,
        status="PENDING_MANAGER_ACTION",
    )
    risk.task = task
    risk.assignment = assignment
    risk.employee = MagicMock()

    service.repo.get_risk_by_id = MagicMock(return_value=risk)

    decision_data = ManagerDecisionCreate(decision="PAUSE", reason="Pause it", pause_classification="Waiting Review")

    with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
        with patch("app.services.task_continuity_service.ProjectMetricsService.recalculate") as mock_recalc:
            with patch("app.services.task_continuity_service.PlanningService.schedule_project") as mock_sched:
                decision = service.resolve_task_risk(risk_id, manager_id, decision_data)
                
                assert task.status == "ON_HOLD"
                assert risk.status == "RESOLVED"
                assert decision.decision == "PAUSE"
                mock_audit.assert_called_once()
                mock_recalc.assert_called_once()
                mock_sched.assert_called_once()


def test_resolve_task_risk_reassign(db, service):
    risk_id = uuid.uuid4()
    manager_id = uuid.uuid4()
    reassign_to = uuid.uuid4()

    task = Task(id=uuid.uuid4(), title="CAD Design", project_id=uuid.uuid4(), status="IN_PROGRESS")
    assignment = TaskAssignment(id=uuid.uuid4(), task_id=task.id, employee_id=uuid.uuid4(), status="ASSIGNED")
    risk = TaskRisk(
        id=risk_id,
        task_id=task.id,
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        remaining_hours=10.0,
        status="PENDING_MANAGER_ACTION",
    )
    risk.task = task
    risk.assignment = assignment
    risk.employee = MagicMock()

    service.repo.get_risk_by_id = MagicMock(return_value=risk)

    decision_data = ManagerDecisionCreate(decision="REASSIGN", reassign_to_id=reassign_to, reason="Reassign to Suresh")

    with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
        with patch("app.services.task_continuity_service.ProjectMetricsService.recalculate") as mock_recalc:
            with patch("app.services.task_continuity_service.PlanningService.schedule_project") as mock_sched:
                decision = service.resolve_task_risk(risk_id, manager_id, decision_data)
                
                assert assignment.status == "CANCELLED"
                assert risk.status == "RESOLVED"
                assert decision.decision == "REASSIGN"
                mock_audit.assert_called_once()
                mock_recalc.assert_called_once()
                mock_sched.assert_called_once()


def test_resolve_task_risk_split(db, service):
    risk_id = uuid.uuid4()
    manager_id = uuid.uuid4()
    reassign_to = uuid.uuid4()

    task = Task(id=uuid.uuid4(), task_code="TASK-100", title="CAD Design", project_id=uuid.uuid4(), estimated_hours=40.0, actual_hours=15.0, status="IN_PROGRESS")
    assignment = TaskAssignment(id=uuid.uuid4(), task_id=task.id, employee_id=uuid.uuid4(), status="ASSIGNED")
    risk = TaskRisk(
        id=risk_id,
        task_id=task.id,
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        remaining_hours=25.0,
        status="PENDING_MANAGER_ACTION",
    )
    risk.task = task
    risk.assignment = assignment
    risk.employee = MagicMock()

    service.repo.get_risk_by_id = MagicMock(return_value=risk)
    db.scalars.return_value.first.return_value = None  # No task code conflicts

    decision_data = ManagerDecisionCreate(decision="SPLIT", reassign_to_id=reassign_to, reason="Split task")

    with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
        with patch("app.services.task_continuity_service.ProjectMetricsService.recalculate") as mock_recalc:
            with patch("app.services.task_continuity_service.PlanningService.schedule_project") as mock_sched:
                decision = service.resolve_task_risk(risk_id, manager_id, decision_data)
                
                assert task.status == "PARTIALLY_COMPLETED"
                assert assignment.status == "CANCELLED"
                assert risk.status == "RESOLVED"
                assert decision.decision == "SPLIT"
                mock_audit.assert_called_once()
                mock_recalc.assert_called_once()
                mock_sched.assert_called_once()


def test_resolve_task_risk_delegate(db, service):
    risk_id = uuid.uuid4()
    manager_id = uuid.uuid4()
    delegate_id = uuid.uuid4()

    task = Task(id=uuid.uuid4(), title="CAD Design", project_id=uuid.uuid4(), status="IN_PROGRESS")
    assignment = TaskAssignment(id=uuid.uuid4(), task_id=task.id, employee_id=uuid.uuid4(), status="ASSIGNED")
    risk = TaskRisk(
        id=risk_id,
        task_id=task.id,
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        remaining_hours=10.0,
        status="PENDING_MANAGER_ACTION",
    )
    risk.task = task
    risk.assignment = assignment
    risk.employee = MagicMock()

    service.repo.get_risk_by_id = MagicMock(return_value=risk)

    decision_data = ManagerDecisionCreate(decision="DELEGATE", delegate_id=delegate_id, reason="Delegate to Ganesh")

    with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
        with patch("app.services.task_continuity_service.ProjectMetricsService.recalculate") as mock_recalc:
            with patch("app.services.task_continuity_service.PlanningService.schedule_project") as mock_sched:
                decision = service.resolve_task_risk(risk_id, manager_id, decision_data)
                
                assert assignment.status == "DELEGATED"
                assert risk.status == "RESOLVED"
                assert decision.decision == "DELEGATE"
                mock_audit.assert_called_once()
                mock_recalc.assert_called_once()
                mock_sched.assert_called_once()


def test_resume_delegated_task(db, service):
    delegation_id = uuid.uuid4()
    manager_id = uuid.uuid4()

    task = Task(id=uuid.uuid4(), title="CAD Design", project_id=uuid.uuid4(), status="IN_PROGRESS")
    delegation = TaskDelegation(
        id=delegation_id,
        task_id=task.id,
        owner_id=uuid.uuid4(),
        delegate_id=uuid.uuid4(),
        status="ACTIVE",
    )
    delegation.task = task

    service.repo.get_delegation_by_id = MagicMock(return_value=delegation)

    delegate_assign = TaskAssignment(id=uuid.uuid4(), task_id=task.id, employee_id=delegation.delegate_id, status="ASSIGNED")
    owner_assign = TaskAssignment(id=uuid.uuid4(), task_id=task.id, employee_id=delegation.owner_id, status="DELEGATED")

    db.scalars.side_effect = [
        MagicMock(first=lambda: delegate_assign),
        MagicMock(first=lambda: owner_assign),
    ]

    with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
        with patch("app.services.task_continuity_service.ProjectMetricsService.recalculate") as mock_recalc:
            with patch("app.services.task_continuity_service.PlanningService.schedule_project") as mock_sched:
                service.resume_delegated_task(delegation_id, manager_id)
                
                assert delegation.status == "COMPLETED"
                assert delegate_assign.status == "COMPLETED"
                assert owner_assign.status == "ASSIGNED"
                mock_audit.assert_called_once()
                mock_recalc.assert_called_once()
                mock_sched.assert_called_once()


def test_resume_paused_task(db, service):
    task_id = uuid.uuid4()
    manager_id = uuid.uuid4()

    task = Task(id=task_id, title="CAD Design", project_id=uuid.uuid4(), status="ON_HOLD", progress=0.5, actual_hours=5.0)
    db.get.side_effect = lambda model, id_: task if model == Task else None

    pause_hist = TaskPauseHistory(id=uuid.uuid4(), task_id=task_id, is_active=True)
    service.repo.get_active_pause_history = MagicMock(return_value=pause_hist)

    with patch("app.services.task_continuity_service.AuditService.log") as mock_audit:
        with patch("app.services.task_continuity_service.ProjectMetricsService.recalculate") as mock_recalc:
            with patch("app.services.task_continuity_service.PlanningService.schedule_project") as mock_sched:
                service.resume_paused_task(task_id, manager_id)
                
                assert task.status == "IN_PROGRESS"
                assert pause_hist.is_active is False
                assert pause_hist.resumed_by == manager_id
                mock_audit.assert_called_once()
                mock_recalc.assert_called_once()
                mock_sched.assert_called_once()
