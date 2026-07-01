from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.leave_request import LeaveRequest
from app.models.project import Project
from app.models.task_continuity import (
    TaskRisk,
    TaskPauseHistory,
    TaskTransferHistory,
    TaskDelegation,
    ManagerDecision,
)
from app.models.task_dependency import TaskDependency
from app.repositories.task_continuity_repository import TaskContinuityRepository
from app.schemas.task_continuity import ManagerDecisionCreate
from app.services.working_day_engine import WorkingDayEngine
from app.services.audit_service import AuditService
from app.services.project_metrics_service import ProjectMetricsService
from app.services.planning_service import PlanningService


class TaskContinuityService:

    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.repo = TaskContinuityRepository(db)
        self.current_user_id = current_user_id

    def detect_and_create_task_risks(
        self, employee_id: uuid.UUID, leave_request: LeaveRequest
    ) -> list[TaskRisk]:
        """
        Rule 1 & Rule 2:
        Detect active overlapping task assignments for the employee and create TaskRisk records.
        """
        stmt = (
            select(TaskAssignment)
            .join(Task)
            .where(
                TaskAssignment.employee_id == employee_id,
                TaskAssignment.status != "CANCELLED",
                Task.is_active == True,
                Task.status.in_(
                    ["NOT_STARTED", "IN_PROGRESS", "ON_HOLD", "WAITING_REVIEW"]
                ),
            )
        )
        assignments = self.db.scalars(stmt).all()

        created_risks = []
        for assignment in assignments:
            task = assignment.task
            # Determine dates to check overlap
            start_date = assignment.planned_start_date or task.planned_start_date
            end_date = assignment.planned_end_date or task.planned_end_date

            if not start_date or not end_date:
                continue

            # Check overlap: (start_date <= leave_request.to_date) and (end_date >= leave_request.from_date)
            if start_date <= leave_request.to_date and end_date >= leave_request.from_date:
                # Check if risk already recorded for this assignment and leave request
                existing = self.repo.get_risk_by_assignment_and_leave(
                    assignment.id, leave_request.id
                )
                if existing:
                    continue

                remaining_hours = max(
                    0.0,
                    float(task.estimated_hours or 0) - float(task.actual_hours or 0),
                )

                # Calculate days impacted
                overlap_start = max(start_date, leave_request.from_date)
                overlap_end = min(end_date, leave_request.to_date)
                days_impacted = WorkingDayEngine.count_working_days(
                    overlap_start, overlap_end, self.db
                )

                # Determine Risk Level
                if remaining_hours > 20 or days_impacted >= 3:
                    risk_level = "HIGH"
                elif remaining_hours > 8 or days_impacted >= 1:
                    risk_level = "MEDIUM"
                else:
                    risk_level = "LOW"

                impact_desc = (
                    f"Task '{task.title}' ({task.task_code}) has {remaining_hours:.1f} remaining hours "
                    f"with {days_impacted} working days impacted during the engineer's leave."
                )

                risk_data = {
                    "task_id": task.id,
                    "project_id": task.project_id,
                    "assignment_id": assignment.id,
                    "employee_id": employee_id,
                    "leave_request_id": leave_request.id,
                    "leave_start_date": leave_request.from_date,
                    "leave_end_date": leave_request.to_date,
                    "remaining_hours": remaining_hours,
                    "risk_level": risk_level,
                    "days_impacted": days_impacted,
                    "project_impact": impact_desc,
                    "status": "PENDING_MANAGER_ACTION",
                }

                risk = self.repo.create_risk(risk_data)
                created_risks.append(risk)

                # Audit Log
                AuditService.log(
                    self.db,
                    "task_risk",
                    risk.id,
                    "CREATE",
                    performed_by=self.current_user_id,
                    new_value={
                        "task_id": str(task.id),
                        "assignment_id": str(assignment.id),
                        "risk_level": risk_level,
                        "status": "PENDING_MANAGER_ACTION",
                    },
                )

        self.db.commit()
        return created_risks

    def check_and_create_risk_for_assignment(self, assignment) -> Optional[TaskRisk]:
        """
        Scan a single new/updated assignment against approved leave requests of the engineer.
        """
        start_date = assignment.planned_start_date
        end_date = assignment.planned_end_date
        if not start_date or not end_date:
            task = assignment.task or self.db.get(Task, assignment.task_id)
            if task:
                start_date = start_date or task.planned_start_date
                end_date = end_date or task.planned_end_date

        if not start_date or not end_date:
            return None

        from app.models.leave_request import LeaveRequest
        from app.models.task_continuity import TaskRisk
        from sqlalchemy import select

        stmt = (
            select(LeaveRequest)
            .where(
                LeaveRequest.employee_id == assignment.employee_id,
                LeaveRequest.status == "APPROVED",
                LeaveRequest.from_date <= end_date,
                LeaveRequest.to_date >= start_date,
            )
        )
        leaves = self.db.scalars(stmt).all()

        for leave in leaves:
            existing = self.repo.get_risk_by_assignment_and_leave(
                assignment.id, leave.id
            )
            if existing:
                continue

            task = assignment.task or self.db.get(Task, assignment.task_id)
            if not task:
                continue

            remaining_hours = max(
                0.0,
                float(task.estimated_hours or 0) - float(task.actual_hours or 0),
            )

            overlap_start = max(start_date, leave.from_date)
            overlap_end = min(end_date, leave.to_date)
            days_impacted = WorkingDayEngine.count_working_days(
                overlap_start, overlap_end, self.db
            )

            if days_impacted <= 0:
                continue

            if remaining_hours > 20 or days_impacted >= 3:
                risk_level = "HIGH"
            elif remaining_hours > 8 or days_impacted >= 1:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            impact_desc = (
                f"Task '{task.title}' ({task.task_code}) has {remaining_hours:.1f} remaining hours "
                f"with {days_impacted} working days impacted during the engineer's leave."
            )

            risk_data = {
                "task_id": task.id,
                "project_id": task.project_id,
                "assignment_id": assignment.id,
                "employee_id": assignment.employee_id,
                "leave_request_id": leave.id,
                "leave_start_date": leave.from_date,
                "leave_end_date": leave.to_date,
                "remaining_hours": remaining_hours,
                "risk_level": risk_level,
                "days_impacted": days_impacted,
                "project_impact": impact_desc,
                "status": "PENDING_MANAGER_ACTION",
            }

            risk = self.repo.create_risk(risk_data)

            AuditService.log(
                self.db,
                "task_risk",
                risk.id,
                "CREATE",
                performed_by=self.current_user_id,
                new_value={
                    "task_id": str(task.id),
                    "assignment_id": str(assignment.id),
                    "risk_level": risk_level,
                    "status": "PENDING_MANAGER_ACTION",
                },
            )
            self.db.commit()
            return risk
        return None

    def resolve_task_risk(
        self, risk_id: uuid.UUID, manager_id: uuid.UUID, data: ManagerDecisionCreate
    ) -> ManagerDecision:
        """
        Rule 3 & Manager actions.
        Resolves a TaskRisk with one of: CONTINUE, PAUSE, REASSIGN, SPLIT, DELEGATE.
        """
        risk = self.repo.get_risk_by_id(risk_id)
        if not risk:
            raise ValueError(f"Task risk with id {risk_id} not found")
        if risk.status != "PENDING_MANAGER_ACTION":
            raise ValueError(
                f"Task risk is already resolved with status '{risk.status}'"
            )

        task = risk.task
        assignment = risk.assignment
        employee = risk.employee
        decision_upper = data.decision.upper()

        if decision_upper not in ("CONTINUE", "PAUSE", "REASSIGN", "SPLIT", "DELEGATE"):
            raise ValueError("Invalid decision type")

        details = {
            "reason": data.reason,
            "reassign_to_id": str(data.reassign_to_id) if data.reassign_to_id else None,
            "delegate_id": str(data.delegate_id) if data.delegate_id else None,
            "pause_classification": data.pause_classification,
        }

        # 1. Process Decision
        if decision_upper == "CONTINUE":
            # CONTINUE AFTER LEAVE: task remains assigned
            risk.status = "RESOLVED"

            AuditService.log(
                self.db,
                "task_risk",
                risk.id,
                "RESOLVE_CONTINUE",
                performed_by=manager_id,
                old_value={"status": "PENDING_MANAGER_ACTION"},
                new_value={"status": "RESOLVED"},
            )

        elif decision_upper == "PAUSE":
            # PAUSE TASK: Set task status to ON_HOLD
            task.status = "ON_HOLD"

            pause_data = {
                "task_id": task.id,
                "paused_by": manager_id,
                "reason": data.reason or f"Paused due to leave. Category: {data.pause_classification or 'Leave'}",
                "is_active": True,
            }
            self.repo.create_pause_history(pause_data)

            risk.status = "RESOLVED"

            AuditService.log(
                self.db,
                "task",
                task.id,
                "PAUSE",
                performed_by=manager_id,
                old_value={"status": "IN_PROGRESS"},
                new_value={"status": "ON_HOLD"},
            )

        elif decision_upper == "REASSIGN":
            if not data.reassign_to_id:
                raise ValueError("reassign_to_id is required for REASSIGN action")

            # REASSIGN TASK: Cancel current assignment
            assignment.status = "CANCELLED"

            # Create new assignment
            new_assign = TaskAssignment(
                task_id=task.id,
                employee_id=data.reassign_to_id,
                assigned_by=manager_id,
                assigned_hours=float(risk.remaining_hours),
                planned_start_date=assignment.planned_start_date,
                planned_end_date=assignment.planned_end_date,
                notes=f"Reassigned due to leave. Reason: {data.reason or ''}",
                status="ASSIGNED",
            )
            self.db.add(new_assign)
            self.db.flush()

            # Log Transfer History
            transfer_data = {
                "task_id": task.id,
                "from_employee_id": employee.id,
                "to_employee_id": data.reassign_to_id,
                "remaining_hours": risk.remaining_hours,
                "reason": data.reason or "Reassigned due to engineer leave",
                "manager_id": manager_id,
                "transfer_type": "REASSIGN",
            }
            self.repo.create_transfer_history(transfer_data)

            risk.status = "RESOLVED"

            AuditService.log(
                self.db,
                "task",
                task.id,
                "REASSIGN",
                performed_by=manager_id,
                old_value={"assigned_employee_id": str(employee.id)},
                new_value={"assigned_employee_id": str(data.reassign_to_id)},
            )

        elif decision_upper == "SPLIT":
            if not data.reassign_to_id:
                raise ValueError("reassign_to_id is required for SPLIT action")

            # SPLIT TASK: Original estimated_hours remains unchanged
            # Mark as ON_HOLD (not PARTIALLY_COMPLETED which is non-standard/not in STATUS_TRANSITIONS)
            task.status = "ON_HOLD"
            assignment.status = "CANCELLED"

            # Generate unique code for child task
            base_code = task.task_code
            child_code = f"{base_code}-S1"
            idx = 1
            while True:
                conflict = self.db.scalars(
                    select(Task).where(
                        Task.project_id == task.project_id,
                        Task.task_code == child_code,
                    )
                ).first()
                if not conflict:
                    break
                idx += 1
                child_code = f"{base_code}-S{idx}"

            # Create Child Task
            child_task = Task(
                task_code=child_code,
                project_id=task.project_id,
                team_id=task.team_id,
                parent_task_id=task.id,
                title=f"{task.title} - Split",
                description=task.description,
                scope_of_work_id=task.scope_of_work_id,
                department_category=task.department_category,
                status="NOT_STARTED",
                priority=task.priority,
                estimated_hours=risk.remaining_hours,
                actual_hours=0.0,
                planned_start_date=risk.leave_start_date,
                planned_end_date=task.planned_end_date,
                planned_delivery_date=task.planned_delivery_date,
                progress=0.0,
                remarks=f"Split from parent task {task.task_code}",
                is_active=True,
                created_by=manager_id,
            )
            self.db.add(child_task)
            self.db.flush()

            # Create new assignment for child task
            new_assign = TaskAssignment(
                task_id=child_task.id,
                employee_id=data.reassign_to_id,
                assigned_by=manager_id,
                assigned_hours=float(risk.remaining_hours),
                planned_start_date=child_task.planned_start_date,
                planned_end_date=child_task.planned_end_date,
                notes=f"Assigned child task from split of {task.task_code}",
                status="ASSIGNED",
            )
            self.db.add(new_assign)

            # Inherit dependencies
            deps_out = self.db.scalars(
                select(TaskDependency).where(TaskDependency.task_id == task.id)
            ).all()
            for dep in deps_out:
                new_dep = TaskDependency(
                    task_id=child_task.id,
                    depends_on_task_id=dep.depends_on_task_id,
                    dependency_type=dep.dependency_type,
                )
                self.db.add(new_dep)

            deps_in = self.db.scalars(
                select(TaskDependency).where(
                    TaskDependency.depends_on_task_id == task.id
                )
            ).all()
            for dep in deps_in:
                new_dep = TaskDependency(
                    task_id=dep.task_id,
                    depends_on_task_id=child_task.id,
                    dependency_type=dep.dependency_type,
                )
                self.db.add(new_dep)

            # Log Transfer History
            transfer_data = {
                "task_id": task.id,
                "from_employee_id": employee.id,
                "to_employee_id": data.reassign_to_id,
                "remaining_hours": risk.remaining_hours,
                "reason": f"Split task. Child task: {child_code}",
                "manager_id": manager_id,
                "transfer_type": "SPLIT",
            }
            self.repo.create_transfer_history(transfer_data)

            risk.status = "RESOLVED"

            AuditService.log(
                self.db,
                "task",
                task.id,
                "SPLIT",
                performed_by=manager_id,
                old_value={"status": "IN_PROGRESS"},
                new_value={
                    "status": "ON_HOLD",
                    "child_task_code": child_code,
                },
            )

        elif decision_upper == "DELEGATE":
            if not data.delegate_id:
                raise ValueError("delegate_id is required for DELEGATE action")

            # DELEGATE TASK: set original assignment to DELEGATED
            assignment.status = "DELEGATED"

            # Create new delegate assignment
            delegate_assign = TaskAssignment(
                task_id=task.id,
                employee_id=data.delegate_id,
                assigned_by=manager_id,
                assigned_hours=float(risk.remaining_hours),
                planned_start_date=risk.leave_start_date,
                planned_end_date=risk.leave_end_date,
                notes=f"Temporary delegate for {employee.first_name} {employee.last_name}",
                status="ASSIGNED",
            )
            self.db.add(delegate_assign)

            # Log delegation
            delegation_data = {
                "task_id": task.id,
                "owner_id": employee.id,
                "delegate_id": data.delegate_id,
                "start_date": risk.leave_start_date,
                "end_date": risk.leave_end_date,
                "delegated_by": manager_id,
                "status": "ACTIVE",
            }
            self.repo.create_delegation(delegation_data)

            # Log Transfer History
            transfer_data = {
                "task_id": task.id,
                "from_employee_id": employee.id,
                "to_employee_id": data.delegate_id,
                "remaining_hours": risk.remaining_hours,
                "reason": data.reason or "Delegated temporarily",
                "manager_id": manager_id,
                "transfer_type": "DELEGATE_START",
            }
            self.repo.create_transfer_history(transfer_data)

            risk.status = "RESOLVED"

            AuditService.log(
                self.db,
                "task",
                task.id,
                "DELEGATE",
                performed_by=manager_id,
                old_value={"status": "IN_PROGRESS"},
                new_value={"status": "DELEGATED", "delegate_id": str(data.delegate_id)},
            )

        # 2. Record Decision
        decision_record = {
            "task_risk_id": risk.id,
            "task_id": task.id,
            "manager_id": manager_id,
            "decision": decision_upper,
            "details": details,
        }
        decision = self.repo.create_decision(decision_record)

        self.db.commit()

        # 3. Recalculate Metrics and Planning
        self._recalculate_planning_and_metrics(task.project_id)

        return decision

    def resume_delegated_task(
        self, delegation_id: uuid.UUID, manager_id: uuid.UUID
    ) -> None:
        """
        Resumes delegation, returning execution to the original owner.
        """
        delegation = self.repo.get_delegation_by_id(delegation_id)
        if not delegation:
            raise ValueError(f"Task delegation with id {delegation_id} not found")
        if delegation.status != "ACTIVE":
            raise ValueError("Task delegation is not active")

        task = delegation.task

        # 1. Close Delegation
        delegation.status = "COMPLETED"
        delegation.end_date = date.today()

        # 2. Mark Delegate Assignment as COMPLETE
        stmt = select(TaskAssignment).where(
            TaskAssignment.task_id == task.id,
            TaskAssignment.employee_id == delegation.delegate_id,
            TaskAssignment.status != "CANCELLED",
        )
        delegate_assign = self.db.scalars(stmt).first()
        if delegate_assign:
            delegate_assign.status = "COMPLETED"
            delegate_assign.completed_at = datetime.now(timezone.utc)

        # 3. Restore Owner Assignment status back to ASSIGNED
        stmt_owner = select(TaskAssignment).where(
            TaskAssignment.task_id == task.id,
            TaskAssignment.employee_id == delegation.owner_id,
            TaskAssignment.status == "DELEGATED",
        )
        owner_assign = self.db.scalars(stmt_owner).first()
        if owner_assign:
            owner_assign.status = "ASSIGNED"

        # 4. Log Transfer History
        remaining_hours = max(
            0.0,
            float(task.estimated_hours or 0) - float(task.actual_hours or 0),
        )
        transfer_data = {
            "task_id": task.id,
            "from_employee_id": delegation.delegate_id,
            "to_employee_id": delegation.owner_id,
            "remaining_hours": remaining_hours,
            "reason": "Temporary delegation ended. Returned execution to owner.",
            "manager_id": manager_id,
            "transfer_type": "DELEGATE_END",
        }
        self.repo.create_transfer_history(transfer_data)

        # 5. Audit Log
        AuditService.log(
            self.db,
            "task",
            task.id,
            "RESUME_DELEGATION",
            performed_by=manager_id,
            old_value={"status": "DELEGATED"},
            new_value={"status": "ASSIGNED"},
        )

        self.db.commit()

        # 6. Recalculate
        self._recalculate_planning_and_metrics(task.project_id)

    def resume_paused_task(self, task_id: uuid.UUID, manager_id: uuid.UUID) -> None:
        """
        Resumes a paused task, returning its status and closing pause history.
        """
        task = self.db.get(Task, task_id)
        if not task:
            raise ValueError(f"Task with id {task_id} not found")
        if task.status != "ON_HOLD":
            raise ValueError("Task is not paused (status is not ON_HOLD)")

        # 1. Close Pause History
        pause_hist = self.repo.get_active_pause_history(task.id)
        if pause_hist:
            pause_hist.is_active = False
            pause_hist.resumed_at = datetime.now(timezone.utc)
            pause_hist.resumed_by = manager_id

        # 2. Restore Status to previous status
        # If it has progress or actual hours, return to IN_PROGRESS, otherwise NOT_STARTED
        prev_status = (
            "IN_PROGRESS"
            if (task.progress > 0 or task.actual_hours > 0)
            else "NOT_STARTED"
        )
        task.status = prev_status

        # 3. Audit Log
        AuditService.log(
            self.db,
            "task",
            task.id,
            "RESUME",
            performed_by=manager_id,
            old_value={"status": "ON_HOLD"},
            new_value={"status": prev_status},
        )

        self.db.commit()

        # 4. Recalculate
        self._recalculate_planning_and_metrics(task.project_id)

    def _recalculate_planning_and_metrics(self, project_id: uuid.UUID) -> None:
        """
        Triggers recalculations of Project Metrics and Planning schedules.
        """
        # Recalculate Project Metrics
        try:
            ProjectMetricsService.recalculate(self.db, project_id)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        # Recalculate Gantt/Future scheduling
        try:
            planning_svc = PlanningService(self.db)
            planning_svc.schedule_project(project_id)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
