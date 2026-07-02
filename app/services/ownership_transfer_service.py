from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.department import Department
from app.models.department_head_history import DepartmentHeadHistory
from app.models.employee import Employee
from app.models.employee_offboarding_event import EmployeeOffboardingEvent
from app.models.project import Project
from app.models.project_manager_history import ProjectManagerHistory
from app.models.team_member import TeamMember
from app.schemas.offboarding import (
    OffboardExecuteRequest,
    OffboardExecuteResponse,
    OffboardImpactCategory,
    OffboardImpactItem,
    OffboardImpactResponse,
    OffboardImpactWarning,
)
from app.services.audit_service import AuditService


class OwnershipTransferService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def _validate_successor(self, successor_id: str, employee_id: UUID, label: str) -> None:
        """Validate a successor id used in an offboarding transfer (H5):
        must parse, exist, be active, and not be the employee being offboarded."""
        try:
            sid = UUID(successor_id)
        except (ValueError, AttributeError, TypeError):
            raise ValueError(f"Invalid {label} id: {successor_id}")
        if sid == employee_id:
            raise ValueError(f"The {label} cannot be the employee being offboarded")
        successor = self.db.get(Employee, sid)
        if not successor:
            raise ValueError(f"The {label} ({successor_id}) does not reference an existing employee")
        if not successor.is_active:
            raise ValueError(f"The {label} ({successor_id}) is not an active employee")

    # ------------------------------------------------------------------
    # Impact analysis
    # ------------------------------------------------------------------

    def compute_impact(self, employee_id: UUID) -> OffboardImpactResponse:
        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError(f"Employee {employee_id} not found")

        employee_name = f"{employee.first_name} {employee.last_name}"
        warnings: list[OffboardImpactWarning] = []

        # Direct reports
        direct_reports = self.db.scalars(
            select(Employee).where(
                Employee.reporting_manager_id == employee_id,
                Employee.is_active == True,
            )
        ).all()

        # Teams led
        managed_teams = self.db.scalars(
            select(TeamMember)
            .where(
                TeamMember.employee_id == employee_id,
                TeamMember.role_in_team == "LEAD",
                TeamMember.left_at.is_(None),
            )
            .options(joinedload(TeamMember.team))
        ).all()

        # Departments headed
        headed_depts = self.db.scalars(
            select(Department).where(Department.department_head_id == employee_id)
        ).all()

        # Projects as PM
        pm_projects = self.db.scalars(
            select(Project).where(
                Project.project_manager_id == employee_id,
                Project.is_active == True,
            )
        ).all()

        # Active task assignments
        active_tasks: list = []
        try:
            from app.models.task_assignment import TaskAssignment
            from app.models.task import Task

            task_assignments = self.db.scalars(
                select(TaskAssignment)
                .where(
                    TaskAssignment.employee_id == employee_id,
                    TaskAssignment.is_active == True,
                )
                .options(joinedload(TaskAssignment.task))
            ).all()
            active_tasks = [
                ta.task
                for ta in task_assignments
                if ta.task and ta.task.status not in ("COMPLETED", "CANCELLED")
            ]
        except Exception:
            pass

        # Pending leaves
        pending_leaves: list = []
        try:
            from app.models.leave_request import LeaveRequest

            pending_leaves = self.db.scalars(
                select(LeaveRequest).where(
                    LeaveRequest.employee_id == employee_id,
                    LeaveRequest.status == "PENDING",
                )
            ).all()
        except Exception:
            pass

        # Pending time entries
        pending_entries: list = []
        try:
            from app.models.time_entry import TimeEntry

            pending_entries = self.db.scalars(
                select(TimeEntry).where(
                    TimeEntry.employee_id == employee_id,
                    TimeEntry.status.in_(["DRAFT", "SUBMITTED"]),
                )
            ).all()
        except Exception:
            pass

        # Active project memberships
        memberships: list = []
        try:
            from app.models.project_member import ProjectMember

            memberships = self.db.scalars(
                select(ProjectMember)
                .where(
                    ProjectMember.employee_id == employee_id,
                    ProjectMember.left_at.is_(None),
                )
                .options(joinedload(ProjectMember.project))
            ).all()
        except Exception:
            pass

        # Warnings
        if pm_projects:
            warnings.append(
                OffboardImpactWarning(
                    severity="warning",
                    message=f"{len(pm_projects)} project(s) will have no project manager.",
                )
            )
        if direct_reports:
            warnings.append(
                OffboardImpactWarning(
                    severity="warning",
                    message=f"{len(direct_reports)} direct report(s) need a new reporting manager.",
                )
            )
        if active_tasks:
            warnings.append(
                OffboardImpactWarning(
                    severity="info",
                    message=f"{len(active_tasks)} active task(s) need reassignment.",
                )
            )

        return OffboardImpactResponse(
            employee_id=employee_id,
            employee_name=employee_name,
            current_status=employee.account_status,
            direct_reports=OffboardImpactCategory(
                count=len(direct_reports),
                items=[
                    OffboardImpactItem(id=str(e.id), name=f"{e.first_name} {e.last_name}")
                    for e in direct_reports
                ],
            ),
            teams_led=OffboardImpactCategory(
                count=len(managed_teams),
                items=[
                    OffboardImpactItem(
                        id=str(tm.team_id),
                        name=tm.team.team_name if tm.team else "Unknown",
                    )
                    for tm in managed_teams
                ],
            ),
            departments_headed=OffboardImpactCategory(
                count=len(headed_depts),
                items=[OffboardImpactItem(id=str(d.id), name=d.name) for d in headed_depts],
            ),
            projects_as_pm=OffboardImpactCategory(
                count=len(pm_projects),
                items=[
                    OffboardImpactItem(id=str(p.id), name=p.name, detail=p.project_code)
                    for p in pm_projects
                ],
            ),
            active_tasks=OffboardImpactCategory(
                count=len(active_tasks),
                items=[OffboardImpactItem(id=str(t.id), name=t.title) for t in active_tasks],
            ),
            pending_leaves=OffboardImpactCategory(
                count=len(pending_leaves),
                items=[
                    OffboardImpactItem(id=str(lv.id), name=f"Leave {str(lv.id)[:8]}")
                    for lv in pending_leaves
                ],
            ),
            pending_time_entries=OffboardImpactCategory(
                count=len(pending_entries),
                items=[
                    OffboardImpactItem(id=str(e.id), name=f"Entry {str(e.id)[:8]}")
                    for e in pending_entries
                ],
            ),
            project_memberships=OffboardImpactCategory(
                count=len(memberships),
                items=[
                    OffboardImpactItem(
                        id=str(m.project_id),
                        name=m.project.name if m.project else "Unknown",
                    )
                    for m in memberships
                ],
            ),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Atomic execution
    # ------------------------------------------------------------------

    def execute_offboard(
        self, employee_id: UUID, req: OffboardExecuteRequest
    ) -> OffboardExecuteResponse:
        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError(f"Employee {employee_id} not found")

        employee_name = f"{employee.first_name} {employee.last_name}"
        summary: dict = {}

        from app.services.employee_service import EmployeeService
        emp_svc = EmployeeService(self.db, current_user_id=self.current_user_id)

        # ---- Validation phase (H5): validate all successors BEFORE mutating. ----
        # H6/status: route the terminal transition through the state machine.
        emp_svc._validate_status_transition(employee.account_status, req.final_status)

        # Every successor must be an existing, active employee that is not the
        # person being offboarded.
        if req.new_manager_id and req.direct_report_ids:
            self._validate_successor(req.new_manager_id, employee_id, "new manager")
        if req.new_team_lead_id and req.team_ids:
            self._validate_successor(req.new_team_lead_id, employee_id, "new team lead")
        if req.new_dept_head_id and req.department_ids:
            self._validate_successor(req.new_dept_head_id, employee_id, "new department head")
        for pm_r in req.project_pm_reassignments:
            self._validate_successor(pm_r.new_pm_id, employee_id, "new project manager")
        for tr in req.task_reassignments:
            self._validate_successor(tr.new_assignee_id, employee_id, "new task assignee")
        if req.bulk_task_reassign_to:
            self._validate_successor(req.bulk_task_reassign_to, employee_id, "bulk task assignee")

        # For direct-report reassignment, ensure no reporting cycle is created:
        # the new manager must not (transitively) report to any transferred report.
        if req.new_manager_id and req.direct_report_ids:
            new_mgr_uuid = UUID(req.new_manager_id)
            for rid in req.direct_report_ids:
                emp_svc._detect_circular_reporting(UUID(rid), new_mgr_uuid)

        # 1. Direct reports (+ reporting history)
        if req.new_manager_id and req.direct_report_ids:
            new_mgr = UUID(req.new_manager_id)
            transferred = 0
            for rid in req.direct_report_ids:
                report = self.db.get(Employee, UUID(rid))
                if report and report.reporting_manager_id == employee_id:
                    old_mgr_id = report.reporting_manager_id
                    report.reporting_manager_id = new_mgr
                    emp_svc._record_reporting_change(report, old_mgr_id, new_mgr)
                    transferred += 1
            summary["direct_reports_transferred"] = transferred

        # 2. Team leadership
        if req.new_team_lead_id and req.team_ids:
            new_lead = UUID(req.new_team_lead_id)
            for tid in req.team_ids:
                team_uuid = UUID(tid)
                old_tm = self.db.scalar(
                    select(TeamMember).where(
                        TeamMember.team_id == team_uuid,
                        TeamMember.employee_id == employee_id,
                        TeamMember.left_at.is_(None),
                    )
                )
                if old_tm:
                    old_tm.left_at = datetime.now(timezone.utc)
                new_tm = self.db.scalar(
                    select(TeamMember).where(
                        TeamMember.team_id == team_uuid,
                        TeamMember.employee_id == new_lead,
                    )
                )
                if new_tm:
                    new_tm.left_at = None
                    new_tm.role_in_team = "LEAD"
                else:
                    self.db.add(
                        TeamMember(
                            team_id=team_uuid,
                            employee_id=new_lead,
                            role_in_team="LEAD",
                            joined_at=date.today(),
                        )
                    )
            summary["teams_transferred"] = len(req.team_ids)

        # 3. Department heads + history
        if req.new_dept_head_id and req.department_ids:
            new_head = UUID(req.new_dept_head_id)
            transferred = 0
            for did in req.department_ids:
                dept = self.db.get(Department, UUID(did))
                if dept and dept.department_head_id == employee_id:
                    self.db.add(
                        DepartmentHeadHistory(
                            department_id=dept.id,
                            employee_id=employee_id,
                            from_date=employee.date_of_joining or date.today(),
                            to_date=req.effective_date,
                            reason=req.reason or "Offboarding",
                            changed_by=self.current_user_id,
                        )
                    )
                    dept.department_head_id = new_head
                    transferred += 1
            summary["departments_transferred"] = transferred

        # 4. Project PMs + history
        for pm_r in req.project_pm_reassignments:
            project = self.db.get(Project, UUID(pm_r.project_id))
            if project and project.project_manager_id == employee_id:
                self.db.add(
                    ProjectManagerHistory(
                        project_id=project.id,
                        employee_id=employee_id,
                        from_date=(
                            project.actual_start_date
                            or project.planned_start_date
                            or date.today()
                        ),
                        to_date=req.effective_date,
                        reason=req.reason or "Offboarding",
                        changed_by=self.current_user_id,
                    )
                )
                project.project_manager_id = UUID(pm_r.new_pm_id)
        summary["projects_transferred"] = len(req.project_pm_reassignments)

        # 5. Task reassignments
        reassigned = 0
        try:
            from app.models.task_assignment import TaskAssignment

            for tr in req.task_reassignments:
                ta = self.db.scalar(
                    select(TaskAssignment).where(
                        TaskAssignment.task_id == UUID(tr.task_id),
                        TaskAssignment.employee_id == employee_id,
                        TaskAssignment.is_active == True,
                    )
                )
                if ta:
                    ta.employee_id = UUID(tr.new_assignee_id)
                    reassigned += 1
            if req.bulk_task_reassign_to:
                bulk_id = UUID(req.bulk_task_reassign_to)
                remaining = self.db.scalars(
                    select(TaskAssignment).where(
                        TaskAssignment.employee_id == employee_id,
                        TaskAssignment.is_active == True,
                    )
                ).all()
                for ta in remaining:
                    ta.employee_id = bulk_id
                    reassigned += 1
        except Exception:
            pass
        summary["tasks_reassigned"] = reassigned

        # 6. Close project memberships
        closed_memberships = 0
        try:
            from app.models.project_member import ProjectMember

            memberships = self.db.scalars(
                select(ProjectMember).where(
                    ProjectMember.employee_id == employee_id,
                    ProjectMember.left_at.is_(None),
                )
            ).all()
            for m in memberships:
                m.left_at = req.effective_date
            closed_memberships = len(memberships)
        except Exception:
            pass
        summary["project_memberships_closed"] = closed_memberships

        # 7. Leave disposition
        cancelled_leaves = 0
        try:
            from app.models.leave_request import LeaveRequest

            if req.leave_disposition == "CANCEL_ALL":
                leaves = self.db.scalars(
                    select(LeaveRequest).where(
                        LeaveRequest.employee_id == employee_id,
                        LeaveRequest.status == "PENDING",
                    )
                ).all()
                for lv in leaves:
                    lv.status = "CANCELLED"
                cancelled_leaves = len(leaves)
        except Exception:
            pass
        summary["leaves_cancelled"] = cancelled_leaves

        # 8. Time entry disposition
        processed_entries = 0
        try:
            from app.models.time_entry import TimeEntry

            if req.time_entry_disposition in ("AUTO_APPROVE", "AUTO_REJECT"):
                new_status = (
                    "APPROVED" if req.time_entry_disposition == "AUTO_APPROVE" else "REJECTED"
                )
                entries = self.db.scalars(
                    select(TimeEntry).where(
                        TimeEntry.employee_id == employee_id,
                        TimeEntry.status.in_(["DRAFT", "SUBMITTED"]),
                    )
                ).all()
                for e in entries:
                    e.status = new_status
                processed_entries = len(entries)
        except Exception:
            pass
        summary["time_entries_processed"] = processed_entries

        # 9. Update employee record
        employee.offboard_reason = req.reason
        employee.offboard_initiated_by = self.current_user_id
        if req.final_status == "RESIGNED":
            employee.resignation_date = req.effective_date
        else:
            employee.termination_date = req.effective_date
        employee.last_working_date = req.effective_date
        employee.account_status = req.final_status
        employee.is_active = False

        # 10. Write offboarding event record
        event = EmployeeOffboardingEvent(
            employee_id=employee_id,
            initiated_by=self.current_user_id,
            effective_date=req.effective_date,
            final_status=req.final_status,
            reason=req.reason,
            transfer_summary=summary,
        )
        self.db.add(event)

        AuditService.log(
            self.db,
            "employee",
            employee_id,
            "OFFBOARD_EXECUTE",
            performed_by=self.current_user_id,
            new_value={
                "final_status": req.final_status,
                "effective_date": req.effective_date.isoformat(),
                "reason": req.reason,
                "transfer_summary": summary,
            },
        )

        self.db.flush()

        return OffboardExecuteResponse(
            employee_id=employee_id,
            employee_name=employee_name,
            final_status=req.final_status,
            effective_date=req.effective_date,
            event_id=event.id,
            transfers_completed=summary,
        )
