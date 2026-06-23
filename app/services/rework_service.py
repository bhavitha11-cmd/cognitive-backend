from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.task import Task
from app.models.task_rework_history import TaskReworkHistory
from app.schemas.task_rework import TaskReworkRead
from app.services.audit_service import AuditService
from app.services.project_metrics_service import ProjectMetricsService


class ReworkService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Open a rework cycle ──────────────────────────────────────────────────
    # Rule 5: Reopen a completed task for rework

    def open_rework(
        self,
        task_id: UUID,
        reason: str | None = None,
    ) -> TaskReworkRead:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        task = self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        if not task.is_active:
            raise ValueError("Cannot open rework on an inactive task")

        # Count existing rework cycles
        rework_count = self.db.scalar(
            select(func.count()).select_from(TaskReworkHistory).where(
                TaskReworkHistory.task_id == task_id,
                TaskReworkHistory.closed_at.is_(None),  # open cycles
            )
        ) or 0
        if rework_count > 0:
            raise ValueError(
                "This task already has an open rework cycle. "
                "Close it before opening a new one."
            )

        next_number = (task.rework_count or 0) + 1

        # Save original estimated hours if this is the first rework
        if task.rework_count == 0 and not task.original_estimated_hours:
            task.original_estimated_hours = task.estimated_hours

        # Create rework record
        now = datetime.now(timezone.utc)
        rework = TaskReworkHistory(
            task_id=task_id,
            rework_number=next_number,
            opened_by=self.current_user_id,
            opened_at=now,
            reason=reason,
        )
        self.db.add(rework)

        # Update task status to REOPENED
        task.status = "REOPENED"
        task.rework_count = next_number

        # Store rework count in task
        if not task.actual_start_date:
            task.actual_start_date = now.date()

        project_id = task.project_id

        try:
            self.db.flush()
            self.db.commit()

            AuditService.log(
                self.db,
                "task_rework_history",
                rework.id,
                "REWORK_OPEN",
                performed_by=self.current_user_id,
                new_value={
                    "task_id": str(task_id),
                    "rework_number": next_number,
                    "reason": reason,
                },
            )

            AuditService.log(
                self.db,
                "task",
                task_id,
                "REOPENED",
                performed_by=self.current_user_id,
                new_value={
                    "status": "REOPENED",
                    "rework_count": next_number,
                },
            )
        except Exception:
            self.db.rollback()
            raise

        # Task status changed to REOPENED — project must reflect "In Progress"
        self._trigger_project_recalc(project_id)

        return self._build_read(rework)

    # ── Close a rework cycle ─────────────────────────────────────────────────

    def close_rework(
        self,
        rework_id: UUID,
        hours_spent: float,
    ) -> TaskReworkRead:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        rework = self.db.get(TaskReworkHistory, rework_id)
        if not rework:
            raise ValueError(f"Rework record with id {rework_id} not found")

        if rework.closed_at is not None:
            raise ValueError("This rework cycle is already closed")

        now = datetime.now(timezone.utc)
        rework.closed_at = now
        rework.hours_spent = hours_spent

        # Update task rework totals
        task = self.db.get(Task, rework.task_id)
        task_project_id = task.project_id if task else None
        if task:
            task.total_rework_hours = float(
                self.db.scalar(
                    select(func.sum(TaskReworkHistory.hours_spent)).where(
                        TaskReworkHistory.task_id == task.id,
                        TaskReworkHistory.closed_at.isnot(None),
                    )
                ) or 0
            )

        try:
            self.db.flush()
            self.db.commit()

            AuditService.log(
                self.db,
                "task_rework_history",
                rework.id,
                "REWORK_CLOSE",
                performed_by=self.current_user_id,
                new_value={
                    "task_id": str(rework.task_id),
                    "rework_number": rework.rework_number,
                    "hours_spent": hours_spent,
                },
            )
        except Exception:
            self.db.rollback()
            raise

        if task_project_id:
            self._trigger_project_recalc(task_project_id)

        return self._build_read(rework)

    # ── Get rework history for a task ────────────────────────────────────────

    def get_task_rework_history(self, task_id: UUID) -> list[TaskReworkRead]:
        history = self.db.scalars(
            select(TaskReworkHistory)
            .where(TaskReworkHistory.task_id == task_id)
            .order_by(TaskReworkHistory.rework_number.asc())
        ).all()
        return [self._build_read(h) for h in history]

    # ── Get open rework cycles ───────────────────────────────────────────────

    def get_open_rework_cycles(self) -> list[TaskReworkRead]:
        history = self.db.scalars(
            select(TaskReworkHistory)
            .where(TaskReworkHistory.closed_at.is_(None))
            .order_by(TaskReworkHistory.opened_at.desc())
        ).all()
        return [self._build_read(h) for h in history]

    # ── Internal ─────────────────────────────────────────────────────────────

    def _trigger_project_recalc(self, project_id: UUID) -> None:
        import logging
        try:
            ProjectMetricsService.recalculate(self.db, project_id)
            self.db.commit()
        except Exception:
            logging.getLogger(__name__).warning(
                "[ReworkService] project_metrics recalc failed for project %s",
                project_id, exc_info=True,
            )

    def _build_read(self, rework: TaskReworkHistory) -> TaskReworkRead:
        return TaskReworkRead(
            id=rework.id,
            task_id=rework.task_id,
            rework_number=rework.rework_number,
            opened_by=rework.opened_by,
            opened_at=rework.opened_at,
            closed_at=rework.closed_at,
            reason=rework.reason,
            hours_spent=float(rework.hours_spent),
            created_at=rework.created_at,
        )
