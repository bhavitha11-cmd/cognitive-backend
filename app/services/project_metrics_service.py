"""
ProjectMetricsService
=====================
Centralized service that recomputes ALL project-level derived fields from
tasks and persists them in a single atomic UPDATE.

Fields auto-managed:
  - estimated_hours   → SUM(task.estimated_hours)  [= "planned hours"]
  - actual_hours      → SUM(task.actual_hours)
  - actual_start_date → MIN(task.actual_start_date) where not null
  - actual_end_date   → MAX(task.actual_end_date)   only if ALL tasks closed
  - progress          → SUM(completed_task est_hours) / SUM(all est_hours) * 100
  - status            → priority-rule derivation from task statuses

Invoke via:
    ProjectMetricsService.recalculate(db, project_id)

This is the ONLY place project metrics are written.
Never set these fields directly from any other service.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# ── Status priority order ────────────────────────────────────────────────────
# Maps task UPPER_SNAKE statuses to derived project Title-Case status.
# Rules applied in descending priority.
_TASK_STATUS_PRIORITY: list[tuple[str, str]] = [
    ("IN_PROGRESS", "In Progress"),
    ("REOPENED",    "In Progress"),
    ("ON_HOLD",     "On Hold"),
]

_CLOSED_STATUSES = frozenset({"COMPLETED", "CANCELLED"})


class ProjectMetricsService:
    """Stateless — all methods are class-level for easy import anywhere."""

    @classmethod
    def recalculate(cls, db: Session, project_id: UUID) -> dict[str, Any]:
        """
        Recalculate all derived project metrics from its tasks.
        Persists results in a single UPDATE and writes an audit log entry.
        Returns {"old": {...}, "new": {...}} for caller inspection.
        """
        from app.models.project import Project
        from app.models.task import Task
        from app.services.audit_service import AuditService

        project: Project | None = db.get(Project, project_id)
        if not project or not project.is_active:
            return {}

        # ── 1. Load all active tasks ────────────────────────────────────────
        tasks = db.scalars(
            select(Task).where(
                and_(Task.project_id == project_id, Task.is_active == True)  # noqa: E712
            )
        ).all()

        # ── 2. Compute derived values ────────────────────────────────────────
        new_estimated_hours  = cls._compute_estimated_hours(tasks)
        new_actual_hours     = cls._compute_actual_hours(tasks)
        new_actual_start     = cls._compute_actual_start(tasks)
        new_actual_end       = cls._compute_actual_end(tasks)
        new_progress         = cls._compute_progress(tasks)
        new_status           = cls._compute_status(tasks)

        # ── 3. Capture old values for audit ─────────────────────────────────
        old_values = {
            "estimated_hours":  float(project.estimated_hours  or 0),
            "actual_hours":     float(project.actual_hours     or 0),
            "actual_start_date": str(project.actual_start_date) if project.actual_start_date else None,
            "actual_end_date":   str(project.actual_end_date)   if project.actual_end_date   else None,
            "progress":          float(project.progress         or 0),
            "status":            project.status,
        }

        new_values = {
            "estimated_hours":  new_estimated_hours,
            "actual_hours":     new_actual_hours,
            "actual_start_date": str(new_actual_start) if new_actual_start else None,
            "actual_end_date":   str(new_actual_end)   if new_actual_end   else None,
            "progress":          new_progress,
            "status":            new_status,
        }

        # ── 4. Persist ───────────────────────────────────────────────────────
        project.estimated_hours  = new_estimated_hours
        project.actual_hours     = new_actual_hours
        project.actual_start_date = new_actual_start
        project.actual_end_date  = new_actual_end
        project.progress         = new_progress
        project.status           = new_status

        db.flush()  # write within the caller's transaction

        # ── 5. Audit log — only if anything changed ──────────────────────────
        changed = {k: v for k, v in new_values.items() if str(v) != str(old_values.get(k))}
        if changed:
            try:
                AuditService.log(
                    db,
                    "project",
                    project_id,
                    "AUTO_RECALC",
                    performed_by=None,
                    old_value={k: old_values[k] for k in changed},
                    new_value={k: new_values[k] for k in changed},
                )
            except Exception:
                logger.warning(
                    "[ProjectMetrics] Audit log failed for project %s — skipping.",
                    project_id, exc_info=True,
                )

        logger.debug(
            "[ProjectMetrics] project=%s | est=%.2f act=%.2f prog=%.1f%% status=%s",
            project_id, new_estimated_hours, new_actual_hours, new_progress, new_status,
        )

        return {"old": old_values, "new": new_values}

    # ── Computation helpers ──────────────────────────────────────────────────

    @staticmethod
    def _compute_estimated_hours(tasks: list) -> float:
        """SUM(task.estimated_hours) for all active tasks."""
        return round(sum(float(t.estimated_hours or 0) for t in tasks), 2)

    @staticmethod
    def _compute_actual_hours(tasks: list) -> float:
        """SUM(task.actual_hours) for all active tasks."""
        return round(sum(float(t.actual_hours or 0) for t in tasks), 2)

    @staticmethod
    def _compute_actual_start(tasks: list) -> date | None:
        """MIN(task.actual_start_date) across tasks that have started."""
        dates = [t.actual_start_date for t in tasks if t.actual_start_date]
        return min(dates) if dates else None

    @staticmethod
    def _compute_actual_end(tasks: list) -> date | None:
        """
        MAX(task.actual_end_date) ONLY when every task is COMPLETED or CANCELLED.
        Returns None if any task is still open.
        """
        if not tasks:
            return None
        open_tasks = [t for t in tasks if t.status not in _CLOSED_STATUSES]
        if open_tasks:
            return None  # project still in progress
        # All tasks closed — return the latest end date
        dates = [t.actual_end_date for t in tasks if t.actual_end_date]
        return max(dates) if dates else None

    @staticmethod
    def _compute_progress(tasks: list) -> float:
        """
        Hour-weighted progress:
            SUM(estimated_hours of COMPLETED tasks) / SUM(all estimated_hours) * 100
        Returns 0.0 when there are no tasks or no estimated hours.
        """
        if not tasks:
            return 0.0
        total_est = sum(float(t.estimated_hours or 0) for t in tasks)
        if total_est == 0:
            return 0.0
        completed_est = sum(
            float(t.estimated_hours or 0)
            for t in tasks if t.status == "COMPLETED"
        )
        return round((completed_est / total_est) * 100, 2)

    @staticmethod
    def _compute_status(tasks: list) -> str:
        """
        Derive project status from task statuses using priority rules.

        Priority order:
          1. No tasks → "Yet To Start"
          2. Any IN_PROGRESS → "In Progress"
          3. Any REOPENED   → "In Progress"
          4. All COMPLETED or CANCELLED, at least 1 COMPLETED → "Completed"
          5. All CANCELLED (none COMPLETED) → "Cancelled"
          6. Any ON_HOLD → "On Hold"
          7. All NOT_STARTED (or mixed not-started) → "Yet To Start"
        """
        if not tasks:
            return "Yet To Start"

        statuses = {t.status for t in tasks}

        # Rules 2 & 3 — any open/active state wins
        for task_status, project_status in _TASK_STATUS_PRIORITY:
            if task_status in statuses:
                return project_status

        # Rules 4 & 5 — all tasks are closed
        all_closed = all(t.status in _CLOSED_STATUSES for t in tasks)
        if all_closed:
            has_completed = any(t.status == "COMPLETED" for t in tasks)
            return "Completed" if has_completed else "Cancelled"

        # Rule 6 — explicit on-hold check handled above in priority list
        # Rule 7 — nothing started yet
        return "Yet To Start"
