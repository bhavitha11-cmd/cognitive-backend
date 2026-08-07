from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalInstance, ApprovalWorkflow, ApprovalWorkflowStep
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.role import Role
from app.models.team import Team
from app.models.team_member import TeamMember


class ApprovalService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Workflow Configuration & Validation ───────────────────────────────────

    def get_workflow(self, workflow_id: uuid.UUID) -> ApprovalWorkflow | None:
        return self.db.get(ApprovalWorkflow, workflow_id)

    def get_all_workflows(self, module_type: str | None = None) -> list[ApprovalWorkflow]:
        stmt = select(ApprovalWorkflow)
        if module_type:
            stmt = stmt.where(ApprovalWorkflow.module_type == module_type)
        stmt = stmt.order_by(ApprovalWorkflow.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def create_workflow(self, name: str, module_type: str, approval_strategy: str = "ANY_ONE") -> ApprovalWorkflow:
        # Check if version exists for module
        max_version = self.db.scalar(
            select(func.max(ApprovalWorkflow.version)).where(ApprovalWorkflow.module_type == module_type)
        ) or 0

        workflow = ApprovalWorkflow(
            name=name,
            module_type=module_type.upper(),
            version=max_version + 1,
            approval_strategy=approval_strategy,
            is_active=False,
        )
        self.db.add(workflow)
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    def set_workflow_steps(self, workflow_id: uuid.UUID, steps_data: list[dict]) -> list[ApprovalWorkflowStep]:
        workflow = self.db.get(ApprovalWorkflow, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow with ID {workflow_id} not found")
        if workflow.is_active:
            raise ValueError("Cannot modify steps on an active workflow. Deactivate it or create a new draft version.")

        # Delete existing steps
        self.db.execute(
            select(ApprovalWorkflowStep).where(ApprovalWorkflowStep.workflow_id == workflow_id)
        )
        # SQLAlchemy cascade handles removal, but let's clear explicitly
        for s in list(workflow.steps):
            self.db.delete(s)
        self.db.flush()

        # Group steps by requester_role_id to auto-normalize levels
        steps_by_role = {}
        for step in steps_data:
            role_id = uuid.UUID(str(step["requester_role_id"]))
            steps_by_role.setdefault(role_id, []).append(step)

        # Re-assign sequential levels starting from 1 for each role
        normalized_steps_data = []
        for role_id, role_steps in steps_by_role.items():
            # Sort by original level to preserve configured relative order
            role_steps.sort(key=lambda s: s["level"])
            for idx, step in enumerate(role_steps, start=1):
                step["level"] = idx
                normalized_steps_data.append(step)

        steps = []
        for step in normalized_steps_data:
            new_step = ApprovalWorkflowStep(
                workflow_id=workflow_id,
                requester_role_id=step["requester_role_id"],
                level=step["level"],
                approver_role_id=step["approver_role_id"],
                resolution_scope=step["resolution_scope"],
            )
            self.db.add(new_step)
            steps.append(new_step)

        self.db.commit()
        self.db.refresh(workflow)
        return workflow.steps

    def activate_workflow(self, workflow_id: uuid.UUID) -> ApprovalWorkflow:
        workflow = self.db.get(ApprovalWorkflow, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow with ID {workflow_id} not found")

        # Validation 1: Must have steps
        if not workflow.steps:
            raise ValueError("Cannot activate a workflow with no steps configured.")

        # Group steps by requester_role_id to check validation rules per role
        role_steps_map: dict[uuid.UUID, list[ApprovalWorkflowStep]] = {}
        for step in workflow.steps:
            role_steps_map.setdefault(step.requester_role_id, []).append(step)

        for role_id, steps in role_steps_map.items():
            # Sort by level
            steps.sort(key=lambda x: x.level)

            # Validation 2: Continuous levels starting from 1
            expected_level = 1
            for step in steps:
                if step.level != expected_level:
                    role_obj = self.db.get(Role, role_id)
                    role_name = role_obj.name if role_obj else str(role_id)
                    raise ValueError(
                        f"Gaps found in levels for requester role '{role_name}'. "
                        f"Expected level {expected_level}, found {step.level}."
                    )
                expected_level += 1

            # Validation 3: No duplicate levels
            levels = [s.level for s in steps]
            if len(levels) != len(set(levels)):
                raise ValueError("Duplicate steps configured at the same level.")

        # Activate this workflow and deactivate others of the same module type
        try:
            self.db.execute(
                ApprovalWorkflow.__table__.update()
                .where(ApprovalWorkflow.module_type == workflow.module_type)
                .values(is_active=False)
            )
            workflow.is_active = True
            self.db.commit()
            self.db.refresh(workflow)
            return workflow
        except Exception:
            self.db.rollback()
            raise

    # ── Approver Resolution Logic ─────────────────────────────────────────────

    def resolve_approver_for_step(self, requester_id: uuid.UUID, step: ApprovalWorkflowStep) -> uuid.UUID | None:
        """
        Resolves the employee ID of the approver for a workflow step.
        Returns a resolved employee UUID if a specific approver is found,
        or None if it resolves to a pool (e.g. GLOBAL/DEPARTMENT) or if no manager is found.
        """
        requester = self.db.get(Employee, requester_id)
        if not requester:
            return None

        # 1. REPORTING_HIERARCHY
        if step.resolution_scope == "REPORTING_HIERARCHY":
            curr_id = requester.reporting_manager_id
            if not curr_id:
                return None

            visited = {requester.id}
            temp_id = curr_id
            while temp_id and temp_id not in visited:
                visited.add(temp_id)
                # Check if this manager holds the required role
                role_exists = self.db.scalar(
                    select(EmployeeRole.id).where(
                        EmployeeRole.employee_id == temp_id,
                        EmployeeRole.role_id == step.approver_role_id,
                        EmployeeRole.is_active.is_(True),
                    )
                )
                if role_exists:
                    return temp_id
                # Move up the manager tree
                mgr = self.db.get(Employee, temp_id)
                temp_id = mgr.reporting_manager_id if mgr else None
            
            # Fallback to direct reporting manager if no higher manager has exact role
            return curr_id

        # 2. TEAM_ASSIGNMENT
        elif step.resolution_scope == "TEAM_ASSIGNMENT":
            # Get requester's teams
            team_ids = self.db.scalars(
                select(TeamMember.team_id).where(
                    TeamMember.employee_id == requester.id,
                    TeamMember.left_at.is_(None)
                )
            ).all()

            for tid in team_ids:
                # Find Team Leads in those teams
                leads = self.db.scalars(
                    select(TeamMember.employee_id).where(
                        TeamMember.team_id == tid,
                        TeamMember.left_at.is_(None),
                        or_(
                            TeamMember.role_in_team.ilike("lead%"),
                            TeamMember.role_in_team.ilike("owner%")
                        )
                    )
                ).all()

                for lid in leads:
                    # Check if Lead holds the required role
                    role_exists = self.db.scalar(
                        select(EmployeeRole.id).where(
                            EmployeeRole.employee_id == lid,
                            EmployeeRole.role_id == step.approver_role_id,
                            EmployeeRole.is_active.is_(True),
                        )
                    )
                    if role_exists:
                        return lid
            return None

        # 3. DEPARTMENT_ASSIGNMENT
        elif step.resolution_scope == "DEPARTMENT_ASSIGNMENT":
            if requester.department_id:
                # Find department members holding the required role
                dept_members = self.db.scalars(
                    select(Employee.id)
                    .join(EmployeeRole, EmployeeRole.employee_id == Employee.id)
                    .where(
                        Employee.department_id == requester.department_id,
                        Employee.is_active.is_(True),
                        EmployeeRole.role_id == step.approver_role_id,
                        EmployeeRole.is_active.is_(True),
                    )
                ).all()
                if dept_members:
                    return dept_members[0]  # Return first resolved candidate as specific target
            return None

        # 4. GLOBAL
        elif step.resolution_scope == "GLOBAL":
            global_members = self.db.scalars(
                select(Employee.id)
                .join(EmployeeRole, EmployeeRole.employee_id == Employee.id)
                .where(
                    Employee.is_active.is_(True),
                    EmployeeRole.role_id == step.approver_role_id,
                    EmployeeRole.is_active.is_(True),
                )
            ).all()
            if global_members:
                return global_members[0]  # Return first resolved candidate as specific target
            return None

        return None

    # ── Approval Instances Lifecycle ──────────────────────────────────────────

    def initialize_approval_flow(self, module_type: str, target_id: uuid.UUID, requester_id: uuid.UUID) -> Literal["PENDING", "APPROVED"]:
        """
        Creates ApprovalInstance steps for a submitted request.
        Sets the first active level to PENDING and returns the overall workflow status (PENDING or APPROVED).
        """
        # Fetch active workflow for module
        mod_upper = module_type.upper()
        if mod_upper in ("TIME SHEET", "TIMESHEET", "TIME_ENTRY"):
            target_modules = ["TIME SHEET", "TIMESHEET", "TIME_ENTRY"]
        else:
            target_modules = [mod_upper]

        workflow = self.db.scalars(
            select(ApprovalWorkflow).where(
                ApprovalWorkflow.module_type.in_(target_modules),
                ApprovalWorkflow.is_active.is_(True),
            )
        ).first()

        if not workflow:
            raise ValueError(
                f"No active approval workflow configured for module '{module_type}'. "
                "Submission is blocked. Please contact your administrator."
            )

        # Get requester's roles
        req_role_ids = self.db.scalars(
            select(EmployeeRole.role_id).where(
                EmployeeRole.employee_id == requester_id,
                EmployeeRole.is_active.is_(True),
            )
        ).all()

        # Find matching steps
        steps = self.db.scalars(
            select(ApprovalWorkflowStep).where(
                ApprovalWorkflowStep.workflow_id == workflow.id,
                ApprovalWorkflowStep.requester_role_id.in_(req_role_ids),
            )
        ).all()

        # Sort steps by level
        sorted_steps = sorted(steps, key=lambda x: x.level)

        instances: list[ApprovalInstance] = []
        now = datetime.now(timezone.utc)

        for step in sorted_steps:
            resolved_approver = self.resolve_approver_for_step(requester_id, step)

            # Check self-approval
            is_self = resolved_approver == requester_id
            status = "SKIPPED" if is_self else "DRAFT"

            # If it's a hierarchy/team scope and no approver resolved, skip it
            if not resolved_approver and step.resolution_scope in ("REPORTING_HIERARCHY", "TEAM_ASSIGNMENT"):
                status = "SKIPPED"

            instance = ApprovalInstance(
                module_type=module_type.upper(),
                target_id=target_id,
                workflow_id=workflow.id,
                workflow_version=workflow.version,
                level=step.level,
                approver_role_id=step.approver_role_id,
                assigned_approver_id=resolved_approver,
                status=status,
                resolved_by_scope=step.resolution_scope,
                resolved_approver_id=resolved_approver,
                resolution_time=now if resolved_approver else None,
            )
            self.db.add(instance)
            instances.append(instance)

        self.db.flush()

        # Find the first non-skipped instance and mark it PENDING
        pending_activated = False
        for inst in sorted(instances, key=lambda x: x.level):
            if inst.status == "DRAFT":
                inst.status = "PENDING"
                pending_activated = True
                break

        if not pending_activated:
            # All steps were skipped (or there were no steps) -> auto-approved!
            return "APPROVED"

        return "PENDING"

    def get_pending_approvals(self, employee_id: uuid.UUID) -> list[ApprovalInstance]:
        """
        Lists all approval instances currently awaiting action from this employee.
        """
        # Fetch requester roles
        role_ids = self.db.scalars(
            select(EmployeeRole.role_id).where(
                EmployeeRole.employee_id == employee_id,
                EmployeeRole.is_active.is_(True),
            )
        ).all()

        # Get all PENDING instances
        pending_instances = self.db.scalars(
            select(ApprovalInstance).where(
                ApprovalInstance.status == "PENDING"
            )
        ).all()

        my_approvals = []
        for inst in pending_instances:
            # 1. Explicit Assignment
            if inst.assigned_approver_id == employee_id:
                my_approvals.append(inst)
                continue

            # 2. Pool Assignment (assigned_approver_id is None)
            if inst.assigned_approver_id is None:
                # User must hold the required role
                if inst.approver_role_id in role_ids:
                    # Validate scope
                    requester = self.db.get(Employee, self._get_requester_id_for_target(inst.module_type, inst.target_id))
                    if not requester:
                        continue

                    if inst.resolved_by_scope == "GLOBAL":
                        my_approvals.append(inst)
                    elif inst.resolved_by_scope == "DEPARTMENT_ASSIGNMENT":
                        employee = self.db.get(Employee, employee_id)
                        if employee and employee.department_id == requester.department_id:
                            my_approvals.append(inst)
                    elif inst.resolved_by_scope == "TEAM_ASSIGNMENT":
                        # Must be a LEAD in requester's team
                        req_teams = self.db.scalars(
                            select(TeamMember.team_id).where(
                                TeamMember.employee_id == requester.id,
                                TeamMember.left_at.is_(None)
                            )
                        ).all()
                        is_lead = self.db.scalar(
                            select(TeamMember.id).where(
                                TeamMember.team_id.in_(req_teams),
                                TeamMember.employee_id == employee_id,
                                TeamMember.left_at.is_(None),
                                or_(
                                    TeamMember.role_in_team.ilike("lead%"),
                                    TeamMember.role_in_team.ilike("owner%")
                                )
                            )
                        )
                        if is_lead:
                            my_approvals.append(inst)

        return my_approvals

    def _get_all_subordinate_ids(self, manager_id: uuid.UUID) -> set[uuid.UUID]:
        """
        Recursively finds all direct and indirect subordinate employee IDs under a manager.
        """
        subordinates: set[uuid.UUID] = set()
        to_visit = [manager_id]
        while to_visit:
            curr = to_visit.pop()
            children = self.db.scalars(
                select(Employee.id).where(Employee.reporting_manager_id == curr)
            ).all()
            for child_id in children:
                if child_id not in subordinates:
                    subordinates.add(child_id)
                    to_visit.append(child_id)
        return subordinates

    def get_approval_history(self, user_id: uuid.UUID, module_type: str | None = None, limit: int = 50) -> list[ApprovalInstance]:
        """
        Retrieves actioned approval instances (APPROVED or REJECTED)
        where the given user or any subordinate manager in their management tree was the actioner or assigned approver.
        """
        subordinate_ids = self._get_all_subordinate_ids(user_id)
        allowed_ids = {user_id}.union(subordinate_ids)

        query = select(ApprovalInstance).where(
            ApprovalInstance.status.in_(["APPROVED", "REJECTED"]),
            or_(
                ApprovalInstance.actioned_by_id.in_(allowed_ids),
                ApprovalInstance.assigned_approver_id.in_(allowed_ids),
            )
        )
        if module_type:
            mod_upper = module_type.upper()
            if mod_upper in ("TIME SHEET", "TIMESHEET", "TIME_ENTRY"):
                query = query.where(ApprovalInstance.module_type.in_(["TIME SHEET", "TIMESHEET", "TIME_ENTRY"]))
            else:
                query = query.where(ApprovalInstance.module_type == mod_upper)

        query = query.order_by(ApprovalInstance.actioned_at.desc()).limit(limit)
        return list(self.db.scalars(query).all())

    def submit_approval_action(
        self, employee_id: uuid.UUID, instance_id: uuid.UUID, action: Literal["APPROVED", "REJECTED"], comments: str | None = None
    ) -> tuple[str, str | None]:
        """
        Submits an approval action.
        Returns a tuple of (overall_status, rejection_reason).
        """
        instance = self.db.get(ApprovalInstance, instance_id)
        if not instance:
            raise ValueError(f"Approval instance with ID {instance_id} not found")
        if instance.status != "PENDING":
            raise ValueError(f"Approval instance is not in PENDING status. Current status: {instance.status}")

        # Check authorization
        authorized = False
        if instance.assigned_approver_id == employee_id:
            authorized = True
        elif instance.assigned_approver_id is None:
            # Validate pool roles/scopes
            role_ids = self.db.scalars(
                select(EmployeeRole.role_id).where(
                    EmployeeRole.employee_id == employee_id,
                    EmployeeRole.is_active.is_(True),
                )
            ).all()
            if instance.approver_role_id in role_ids:
                requester_id = self._get_requester_id_for_target(instance.module_type, instance.target_id)
                requester = self.db.get(Employee, requester_id)
                if requester:
                    if instance.resolved_by_scope == "GLOBAL":
                        authorized = True
                    elif instance.resolved_by_scope == "DEPARTMENT_ASSIGNMENT":
                        employee = self.db.get(Employee, employee_id)
                        if employee and employee.department_id == requester.department_id:
                            authorized = True
                    elif instance.resolved_by_scope == "TEAM_ASSIGNMENT":
                        req_teams = self.db.scalars(
                            select(TeamMember.team_id).where(
                                TeamMember.employee_id == requester.id,
                                TeamMember.left_at.is_(None)
                            )
                        ).all()
                        is_lead = self.db.scalar(
                            select(TeamMember.id).where(
                                TeamMember.team_id.in_(req_teams),
                                TeamMember.employee_id == employee_id,
                                TeamMember.left_at.is_(None),
                                or_(
                                    TeamMember.role_in_team.ilike("lead%"),
                                    TeamMember.role_in_team.ilike("owner%")
                                )
                            )
                        )
                        if is_lead:
                            authorized = True

        if not authorized:
            raise ValueError("You are not authorized to action this approval step.")

        now = datetime.now(timezone.utc)
        instance.status = action
        instance.actioned_by_id = employee_id
        instance.actioned_at = now
        instance.comments = comments

        try:
            # Triggered by this action
            if action == "REJECTED":
                # Cancel all other steps for this target
                self.db.execute(
                    ApprovalInstance.__table__.update()
                    .where(
                        ApprovalInstance.target_id == instance.target_id,
                        ApprovalInstance.module_type == instance.module_type,
                        ApprovalInstance.status.in_(["PENDING", "DRAFT"]),
                    )
                    .values(status="REJECTED")
                )
                self.db.flush()
                self._update_target_status(instance.module_type, instance.target_id, "REJECTED", comments or "Rejected by approver.", employee_id)
                self.db.commit()
                return "REJECTED", comments or "Rejected by approver."

            else:  # APPROVED
                # Find next DRAFT step
                next_step = self.db.scalars(
                    select(ApprovalInstance)
                    .where(
                        ApprovalInstance.target_id == instance.target_id,
                        ApprovalInstance.module_type == instance.module_type,
                        ApprovalInstance.status == "DRAFT",
                    )
                    .order_by(ApprovalInstance.level)
                ).first()

                if next_step:
                    next_step.status = "PENDING"
                    self.db.flush()
                    self.db.commit()
                    return "PENDING", None
                else:
                    # No more steps left! Overall request is approved.
                    self._update_target_status(instance.module_type, instance.target_id, "APPROVED", None, employee_id)
                    self.db.commit()
                    return "APPROVED", None
        except Exception:
            self.db.rollback()
            raise

    def _get_requester_id_for_target(self, module_type: str, target_id: uuid.UUID) -> uuid.UUID:
        """
        Internal helper to resolve the requester ID from a target object (e.g. LeaveRequest or TimeEntry).
        """
        mod_upper = module_type.upper()
        if mod_upper == "LEAVE":
            from app.models.leave_request import LeaveRequest
            req = self.db.get(LeaveRequest, target_id)
            if req:
                return req.employee_id
        elif mod_upper in ("TIME SHEET", "TIMESHEET", "TIME_ENTRY"):
            from app.models.time_entry import TimeEntry
            entry = self.db.get(TimeEntry, target_id)
            if entry:
                return entry.employee_id
        elif mod_upper == "ATTENDANCE_CORRECTION":
            from app.models.missed_clockin_request import MissedClockinRequest
            from app.models.missed_clockout_request import MissedClockoutRequest
            req = self.db.get(MissedClockinRequest, target_id) or self.db.get(
                MissedClockoutRequest, target_id
            )
            if req:
                return req.employee_id
        raise ValueError(f"Unsupported module type '{module_type}' or target ID not found.")

    def _update_target_status(
        self, module_type: str, target_id: uuid.UUID, status: str, comments: str | None, actioned_by: uuid.UUID
    ) -> None:
        mod_upper = module_type.upper()
        if mod_upper == "LEAVE":
            from app.models.leave_request import LeaveRequest
            req = self.db.get(LeaveRequest, target_id)
            if req:
                req.status = status
                if status == "REJECTED":
                    req.rejection_reason = comments
                elif status == "APPROVED":
                    req.approved_by = actioned_by
                    req.approved_at = datetime.now(timezone.utc)
                    # Recompute used leaves
                    year = req.from_date.year
                    self._recompute_leave_used(req.employee_id, req.leave_type_id, year)
                    # Create ON_LEAVE attendance records
                    from app.services.leave_service import LeaveService
                    leave_svc = LeaveService(self.db, actioned_by)
                    leave_svc._create_on_leave_attendance(req, actioned_by)
                    # Trigger task continuity
                    try:
                        from app.services.task_continuity_service import TaskContinuityService
                        continuity_svc = TaskContinuityService(self.db, actioned_by)
                        continuity_svc.detect_and_create_task_risks(req.employee_id, req)
                    except Exception:
                        pass
                self.db.add(req)
                self.db.flush()
        elif mod_upper in ("TIME SHEET", "TIMESHEET", "TIME_ENTRY"):
            from app.models.time_entry import TimeEntry
            entry = self.db.get(TimeEntry, target_id)
            if entry:
                entry.status = status
                if status == "REJECTED":
                    entry.rejection_reason = comments
                elif status == "APPROVED":
                    entry.approved_by = actioned_by
                    entry.approved_at = datetime.now(timezone.utc)
                    entry.rejection_reason = None
                self.db.add(entry)
                self.db.flush()

                # Recompute task actual hours & project metrics
                from app.services.time_entry_service import TimeEntryService
                te_svc = TimeEntryService(self.db, actioned_by)
                te_svc._recompute_task_actual_hours(entry.task_id)
        elif mod_upper == "ATTENDANCE_CORRECTION":
            from app.models.missed_clockin_request import MissedClockinRequest
            from app.models.missed_clockout_request import MissedClockoutRequest
            from app.services.attendance_service import AttendanceService
            att_svc = AttendanceService(self.db, actioned_by)
            req_in = self.db.get(MissedClockinRequest, target_id)
            if req_in:
                att_svc._finalize_missed_clockin_decision(req_in, status, actioned_by, comments)
            else:
                req_out = self.db.get(MissedClockoutRequest, target_id)
                if req_out:
                    att_svc._finalize_missed_clockout_decision(req_out, status, actioned_by, comments)

    def _recompute_leave_used(self, employee_id: uuid.UUID, leave_type_id: uuid.UUID, year: int) -> None:
        from app.models.leave_balance import LeaveBalance
        from app.models.leave_request import LeaveRequest
        total_used = self.db.scalar(
            select(func.coalesce(func.sum(LeaveRequest.total_days), 0)).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.leave_type_id == leave_type_id,
                LeaveRequest.status == "APPROVED",
                func.extract("year", LeaveRequest.from_date) == year,
            )
        ) or 0.0

        balance = self.db.scalars(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == year,
            )
        ).first()
        if balance:
            balance.used = float(total_used)
            self.db.add(balance)
            self.db.flush()
