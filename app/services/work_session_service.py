from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.task_work_session import TaskWorkSession
from app.models.time_entry import TimeEntry
from app.schemas.work_session import (
    ActiveSessionResponse,
    DailySessionSummary,
    WorkSessionRead,
)
from app.services.audit_service import AuditService
from app.services.project_metrics_service import ProjectMetricsService


class WorkSessionService:
    SESSION_STATUSES = {
        "RUNNING",
        "PAUSED",
        "COMPLETED",
        "CANCELLED",
        "ABANDONED",
    }

    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Start a new work session ──────────────────────────────────────────────

    def start_session(
        self,
        task_id: UUID,
        project_id: UUID,
        session_type: str = "REGULAR",
    ) -> WorkSessionRead:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        employee_id = self.current_user_id

        # Validate employee
        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError("Employee not found")

        # Validate task
        task = self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        if not task.is_active:
            raise ValueError("Cannot start a session on an inactive task")

        # Validate project
        project = self.db.get(Project, project_id)
        if not project:
            raise ValueError("Project not found")

        # Rule 10: Check no overlapping RUNNING/PAUSED sessions for same task+employee
        overlapping = self.db.scalar(
            select(func.count()).select_from(TaskWorkSession).where(
                TaskWorkSession.employee_id == employee_id,
                TaskWorkSession.task_id == task_id,
                TaskWorkSession.status.in_(["RUNNING", "PAUSED"]),
            )
        )
        if overlapping and overlapping > 0:
            raise ValueError(
                "You already have an active or paused session for this task"
            )

        # Rule 1: Check for any other RUNNING session (different task)
        existing_active = self.db.scalar(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == employee_id,
                TaskWorkSession.status == "RUNNING",
            )
        )
        if existing_active:
            # Rule 2: Auto-pause the existing running session
            now = datetime.now(timezone.utc)
            existing_active.end_time = now
            existing_active.status = "PAUSED"
            diff = (now - existing_active.start_time).total_seconds() / 60.0
            existing_active.duration_minutes += int(diff)
            existing_active.pause_reason = (
                f"Auto-paused: new session started for task {task_id}"
            )
            self.db.flush()

            AuditService.log(
                self.db,
                "task_work_session",
                existing_active.id,
                "AUTO_PAUSE",
                performed_by=self.current_user_id,
                new_value={
                    "paused_for_task": str(task_id),
                    "duration_minutes": existing_active.duration_minutes,
                },
            )

        # Rule 6: Check attendance — must be clocked in today
        today = datetime.now(timezone.utc).date()
        attendance = self.db.scalar(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == today,
                Attendance.clock_in.isnot(None),
                Attendance.clock_out.is_(None),
            )
        )
        if not attendance:
            raise ValueError(
                "You must be clocked in before starting a task session. "
                "Please clock in via attendance."
            )

        # Check task assignment
        assignment = self.db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.employee_id == employee_id,
                TaskAssignment.status != "CANCELLED",
            )
        )
        if not assignment:
            raise ValueError(
                "You are not assigned to this task. "
                "Please request assignment from your manager."
            )

        # Create the session
        now = datetime.now(timezone.utc)
        session = TaskWorkSession(
            employee_id=employee_id,
            task_id=task_id,
            project_id=project_id,
            session_type=session_type,
            start_time=now,
            status="RUNNING",
            started_by=self.current_user_id,
        )
        self.db.add(session)

        # Auto-update task status to IN_PROGRESS if not started
        if task.status in ("NOT_STARTED", "YET_TO_START", "YET TO START"):
            task.status = "IN_PROGRESS"
            if not task.actual_start_date:
                task.actual_start_date = today
            self.db.flush()

        try:
            self.db.flush()
            self.db.commit()
            AuditService.log(
                self.db,
                "task_work_session",
                session.id,
                "START",
                performed_by=self.current_user_id,
                new_value={
                    "task_id": str(task_id),
                    "project_id": str(project_id),
                    "session_type": session_type,
                },
            )
        except Exception:
            self.db.rollback()
            raise

        # Task status may have changed to IN_PROGRESS — recalculate project metrics
        self._trigger_project_recalc(project_id)

        return self._build_read(session)

    # ── Pause a session ───────────────────────────────────────────────────────

    def pause_session(
        self, session_id: UUID, reason: str | None = None
    ) -> WorkSessionRead:
        session = self._get_session_or_raise(session_id)

        if session.employee_id != self.current_user_id:
            raise ValueError("You can only pause your own sessions")

        if session.status != "RUNNING":
            raise ValueError(
                f"Cannot pause a session with status '{session.status}'. "
                "Only RUNNING sessions can be paused."
            )

        now = datetime.now(timezone.utc)
        session.end_time = now
        session.status = "PAUSED"
        diff = (now - session.start_time).total_seconds() / 60.0
        session.duration_minutes += int(diff)
        session.pause_reason = reason or session.pause_reason

        try:
            self.db.commit()
            AuditService.log(
                self.db,
                "task_work_session",
                session.id,
                "PAUSE",
                performed_by=self.current_user_id,
                new_value={
                    "duration_minutes": session.duration_minutes,
                    "reason": reason,
                },
            )
        except Exception:
            self.db.rollback()
            raise

        return self._build_read(session)

    # ── Resume a paused session ───────────────────────────────────────────────

    def resume_session(self, session_id: UUID) -> WorkSessionRead:
        session = self._get_session_or_raise(session_id)

        if session.employee_id != self.current_user_id:
            raise ValueError("You can only resume your own sessions")

        if session.status != "PAUSED":
            raise ValueError(
                f"Cannot resume a session with status '{session.status}'. "
                "Only PAUSED sessions can be resumed."
            )

        # Rule 1: Check no other RUNNING session exists
        existing_active = self.db.scalar(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == self.current_user_id,
                TaskWorkSession.status == "RUNNING",
                TaskWorkSession.id != session_id,
            )
        )
        if existing_active:
            raise ValueError(
                "You already have a running session. "
                "Pause or complete it before resuming this one."
            )

        now = datetime.now(timezone.utc)
        session.start_time = now
        session.end_time = None
        session.status = "RUNNING"
        session.pause_reason = None

        try:
            self.db.commit()
            AuditService.log(
                self.db,
                "task_work_session",
                session.id,
                "RESUME",
                performed_by=self.current_user_id,
            )
        except Exception:
            self.db.rollback()
            raise

        return self._build_read(session)

    # ── Complete a session ────────────────────────────────────────────────────

    def complete_session(
        self, session_id: UUID, remarks: str | None = None, mark_task_complete: bool = False
    ) -> WorkSessionRead:
        session = self._get_session_or_raise(session_id)

        if session.employee_id != self.current_user_id:
            raise ValueError("You can only complete your own sessions")

        if session.status not in ("RUNNING", "PAUSED"):
            raise ValueError(
                f"Cannot complete a session with status '{session.status}'. "
                "Only RUNNING or PAUSED sessions can be completed."
            )

        now = datetime.now(timezone.utc)
        if session.status == "RUNNING":
            diff = (now - session.start_time).total_seconds() / 60.0
            session.duration_minutes += int(diff)

        session.end_time = now
        session.status = "COMPLETED"
        session.ended_by = self.current_user_id
        if remarks:
            session.remarks = remarks

        # Rule 4: Update task actual_hours from ALL completed sessions
        self._recompute_task_actual_hours(session.task_id)

        # Rule 5: If employee marks the task itself as complete, update Task status
        if mark_task_complete:
            task = self.db.get(Task, session.task_id)
            if task and task.status not in ("COMPLETED", "CANCELLED"):
                task.status = "COMPLETED"
                if not task.actual_end_date:
                    task.actual_end_date = now.date()
                if not task.actual_delivery_date:
                    task.actual_delivery_date = now.date()
                task.progress = 1.0  # Numeric(5,4): 1.0 = 100%
                self.db.flush()

        # Generate a time entry from completed session
        try:
            self._generate_time_entry_from_session(session)
        except Exception:
            pass  # Non-blocking: time entry generation failure should not fail the session

        try:
            self.db.commit()
            AuditService.log(
                self.db,
                "task_work_session",
                session.id,
                "COMPLETE",
                performed_by=self.current_user_id,
                new_value={
                    "duration_minutes": session.duration_minutes,
                    "task_id": str(session.task_id),
                    "task_marked_complete": mark_task_complete,
                },
            )
        except Exception:
            self.db.rollback()
            raise

        # Recalculate project metrics after session completion (actual_hours, progress, status)
        self._trigger_project_recalc(session.project_id)

        return self._build_read(session)

    # ── Cancel a session ──────────────────────────────────────────────────────

    def cancel_session(self, session_id: UUID) -> WorkSessionRead:
        session = self._get_session_or_raise(session_id)

        if session.employee_id != self.current_user_id:
            raise ValueError("You can only cancel your own sessions")

        if session.status not in ("RUNNING", "PAUSED"):
            raise ValueError(
                f"Cannot cancel a session with status '{session.status}'. "
                "Only RUNNING or PAUSED sessions can be cancelled."
            )

        now = datetime.now(timezone.utc)
        if session.status == "RUNNING":
            diff = (now - session.start_time).total_seconds() / 60.0
            session.duration_minutes += int(diff)

        session.end_time = now
        session.status = "CANCELLED"
        session.ended_by = self.current_user_id

        try:
            self.db.commit()
            AuditService.log(
                self.db,
                "task_work_session",
                session.id,
                "CANCEL",
                performed_by=self.current_user_id,
            )
        except Exception:
            self.db.rollback()
            raise

        return self._build_read(session)

    # ── Get active session for current user ───────────────────────────────────

    def get_active_session(self) -> ActiveSessionResponse | None:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        session = self.db.scalar(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == self.current_user_id,
                TaskWorkSession.status == "RUNNING",
            )
        )
        if not session:
            return None

        now = datetime.now(timezone.utc)
        elapsed = int(
            (now - session.start_time).total_seconds() / 60.0
        )

        return ActiveSessionResponse(
            id=session.id,
            task_id=session.task_id,
            project_id=session.project_id,
            session_type=session.session_type,
            start_time=session.start_time,
            elapsed_minutes=elapsed,
            pause_reason=session.pause_reason,
        )

    # ── Get sessions for a task ──────────────────────────────────────────────

    def get_task_sessions(self, task_id: UUID) -> list[WorkSessionRead]:
        sessions = self.db.scalars(
            select(TaskWorkSession)
            .where(TaskWorkSession.task_id == task_id)
            .order_by(TaskWorkSession.start_time.desc())
        ).all()
        return [self._build_read(s) for s in sessions]

    # ── Get my sessions ──────────────────────────────────────────────────────

    def get_my_sessions(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[WorkSessionRead], int]:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        base_q = select(TaskWorkSession).where(
            TaskWorkSession.employee_id == self.current_user_id
        )
        count_q = select(func.count()).select_from(TaskWorkSession).where(
            TaskWorkSession.employee_id == self.current_user_id
        )

        # Apply filters
        if date_from:
            base_q = base_q.where(TaskWorkSession.start_time >= date_from)
            count_q = count_q.where(TaskWorkSession.start_time >= date_from)
        if date_to:
            end_of_day = datetime.combine(
                date_to, datetime.max.time(), tzinfo=timezone.utc
            )
            base_q = base_q.where(TaskWorkSession.start_time <= end_of_day)
            count_q = count_q.where(TaskWorkSession.start_time <= end_of_day)
        if status:
            base_q = base_q.where(TaskWorkSession.status == status)
            count_q = count_q.where(TaskWorkSession.status == status)

        total = self.db.scalar(count_q) or 0
        sessions = self.db.scalars(
            base_q.order_by(TaskWorkSession.start_time.desc())
            .offset(skip)
            .limit(limit)
        ).all()

        return [self._build_read(s) for s in sessions], total

    # ── Daily summary ────────────────────────────────────────────────────────

    def get_daily_summary(
        self,
        employee_id: UUID | None = None,
        summary_date: date | None = None,
    ) -> DailySessionSummary:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        emp_id = employee_id or self.current_user_id
        the_date = summary_date or datetime.now(timezone.utc).date()

        start_of_day = datetime.combine(the_date, datetime.min.time(), tzinfo=timezone.utc)
        end_of_day = datetime.combine(the_date, datetime.max.time(), tzinfo=timezone.utc)

        sessions = self.db.scalars(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == emp_id,
                TaskWorkSession.start_time >= start_of_day,
                TaskWorkSession.start_time <= end_of_day,
            )
        ).all()

        total_session_minutes = sum(
            s.duration_minutes for s in sessions
            if s.status in ("COMPLETED", "CANCELLED", "ABANDONED")
        )

        # Count currently running/paused duration as of now
        now = datetime.now(timezone.utc)
        for s in sessions:
            if s.status == "RUNNING":
                running_diff = int((now - s.start_time).total_seconds() / 60.0)
                total_session_minutes += running_diff

        # Get breaks for this employee on this date
        from app.models.employee_break import EmployeeBreak
        breaks = self.db.scalars(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id == emp_id,
                EmployeeBreak.date == the_date,
            )
        ).all()
        total_break_minutes = sum(b.duration_minutes for b in breaks)

        net_work_minutes = max(0, total_session_minutes - total_break_minutes)

        return DailySessionSummary(
            date=the_date,
            total_session_minutes=total_session_minutes,
            total_break_minutes=total_break_minutes,
            net_work_minutes=net_work_minutes,
            session_count=len(sessions),
        )

    # ── Get all sessions (admin) ──────────────────────────────────────────────

    def get_all_sessions(
        self,
        employee_id: UUID | None = None,
        task_id: UUID | None = None,
        project_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[WorkSessionRead], int]:
        base_q = select(TaskWorkSession)
        count_q = select(func.count()).select_from(TaskWorkSession)

        if employee_id:
            base_q = base_q.where(TaskWorkSession.employee_id == employee_id)
            count_q = count_q.where(TaskWorkSession.employee_id == employee_id)
        if task_id:
            base_q = base_q.where(TaskWorkSession.task_id == task_id)
            count_q = count_q.where(TaskWorkSession.task_id == task_id)
        if project_id:
            base_q = base_q.where(TaskWorkSession.project_id == project_id)
            count_q = count_q.where(TaskWorkSession.project_id == project_id)
        if date_from:
            base_q = base_q.where(TaskWorkSession.start_time >= date_from)
            count_q = count_q.where(TaskWorkSession.start_time >= date_from)
        if date_to:
            end_of_day = datetime.combine(
                date_to, datetime.max.time(), tzinfo=timezone.utc
            )
            base_q = base_q.where(TaskWorkSession.start_time <= end_of_day)
            count_q = count_q.where(TaskWorkSession.start_time <= end_of_day)
        if status:
            base_q = base_q.where(TaskWorkSession.status == status)
            count_q = count_q.where(TaskWorkSession.status == status)

        total = self.db.scalar(count_q) or 0
        sessions = self.db.scalars(
            base_q.order_by(TaskWorkSession.start_time.desc())
            .offset(skip)
            .limit(limit)
        ).all()

        return [self._build_read(s) for s in sessions], total

    # ── Crash recovery: find RUNNING sessions on login ────────────────────────
    # Rule 11

    def get_running_sessions(self) -> list[ActiveSessionResponse]:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        sessions = self.db.scalars(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == self.current_user_id,
                TaskWorkSession.status == "RUNNING",
            )
        ).all()

        now = datetime.now(timezone.utc)
        results = []
        for s in sessions:
            elapsed = int((now - s.start_time).total_seconds() / 60.0)
            results.append(
                ActiveSessionResponse(
                    id=s.id,
                    task_id=s.task_id,
                    project_id=s.project_id,
                    session_type=s.session_type,
                    start_time=s.start_time,
                    elapsed_minutes=elapsed,
                    pause_reason=s.pause_reason,
                )
            )
        return results

    # ── Clock-out auto-close ──────────────────────────────────────────────────
    # Rule 7

    def end_current_session_on_clock_out(self) -> str | None:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        session = self.db.scalar(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == self.current_user_id,
                TaskWorkSession.status == "RUNNING",
            )
        )
        if not session:
            return None

        now = datetime.now(timezone.utc)
        diff = int((now - session.start_time).total_seconds() / 60.0)
        session.duration_minutes += diff
        session.end_time = now
        session.status = "ABANDONED"
        session.ended_by = self.current_user_id
        session.pause_reason = "Auto-closed on clock-out"

        AuditService.log(
            self.db,
            "task_work_session",
            session.id,
            "AUTO_CLOSE_CLOCK_OUT",
            performed_by=self.current_user_id,
            new_value={
                "duration_minutes": session.duration_minutes,
                "status": "ABANDONED",
            },
        )

        return str(session.id)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_session_or_raise(self, session_id: UUID) -> TaskWorkSession:
        session = self.db.get(TaskWorkSession, session_id)
        if not session:
            raise ValueError(f"Work session with id {session_id} not found")
        return session

    def _trigger_project_recalc(self, project_id: UUID) -> None:
        """Fire-and-forget project metrics recalculation after session events."""
        import logging
        try:
            ProjectMetricsService.recalculate(self.db, project_id)
            self.db.commit()
        except Exception:
            logging.getLogger(__name__).warning(
                "[WorkSessionService] project_metrics recalc failed for project %s",
                project_id, exc_info=True,
            )

    def _recompute_task_actual_hours(self, task_id: UUID) -> None:
        """Use non-REJECTED time entries as the single source of truth, matching TimeEntryService."""
        total = self.db.scalar(
            select(func.sum(TimeEntry.hours_spent)).where(
                TimeEntry.task_id == task_id,
                TimeEntry.status.not_in(["REJECTED"]),
            )
        ) or 0

        task = self.db.get(Task, task_id)
        if task:
            task.actual_hours = round(float(total), 2)
            self.db.flush()

    def _generate_time_entry_from_session(self, session: TaskWorkSession) -> None:
        if not session.duration_minutes or session.duration_minutes < 1:
            return

        session_date = session.start_time.date()
        hours = round(session.duration_minutes / 60.0, 2)

        # Prevent duplicate time entry generation
        existing = self.db.scalar(
            select(TimeEntry).where(
                TimeEntry.employee_id == session.employee_id,
                TimeEntry.task_id == session.task_id,
                TimeEntry.date == session_date,
                TimeEntry.description == f"Session: {session.id}",
            )
        )
        if existing:
            return

        entry = TimeEntry(
            employee_id=session.employee_id,
            task_id=session.task_id,
            project_id=session.project_id,
            date=session_date,
            hours_spent=hours,
            description=f"Session: {session.id}",
            entry_type="REGULAR",
            is_billable=True,
            status="DRAFT",
        )
        self.db.add(entry)
        self.db.flush()

        AuditService.log(
            self.db,
            "time_entry",
            entry.id,
            "CREATE_FROM_SESSION",
            performed_by=self.current_user_id,
            new_value={
                "session_id": str(session.id),
                "hours": hours,
            },
        )

    def _build_read(self, session: TaskWorkSession) -> WorkSessionRead:
        return WorkSessionRead(
            id=session.id,
            employee_id=session.employee_id,
            task_id=session.task_id,
            project_id=session.project_id,
            session_type=session.session_type,
            start_time=session.start_time,
            end_time=session.end_time,
            duration_minutes=session.duration_minutes,
            status=session.status,
            started_by=session.started_by,
            ended_by=session.ended_by,
            pause_reason=session.pause_reason,
            remarks=session.remarks,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
