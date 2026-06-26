from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.models.project import Project
from app.models.task import Task
from app.services.working_day_engine import WorkingDayEngine

logger = logging.getLogger("uvicorn.error")


class RecalculationEngine:
    """Identifies affected entities and delegates updates to owning services."""

    @classmethod
    def trigger(
        cls, holiday_id: UUID, action: str, db: Session
    ) -> dict:
        holiday = db.get(Holiday, holiday_id)
        if not holiday:
            return {"error": f"Holiday {holiday_id} not found"}

        holiday_date = holiday.date
        action_lower = action.lower()

        is_addition = action_lower in ("create", "activate")
        is_removal = action_lower in ("delete", "deactivate")
        if not is_addition and not is_removal and action_lower != "update":
            return {"message": f"No action needed for: {action}"}

        if WorkingDayEngine.is_weekend(holiday_date, db):
            logger.info(
                f"[Recalc] Holiday '{holiday.name}' on {holiday_date} is a weekend — skipping"
            )
            return {"message": "Holiday falls on weekend, no recalculation needed"}

        project_ids = cls.identify_affected_projects(holiday_date, db)
        task_ids = cls.identify_affected_tasks(holiday_date, project_ids, db)

        results = {
            "holiday_id": str(holiday_id),
            "action": action,
            "affected_projects": len(project_ids),
            "affected_tasks": len(task_ids),
            "project_adjustments": [],
            "task_adjustments": [],
        }

        for pid in project_ids:
            result = cls._recalculate_project(pid, is_addition, db)
            results["project_adjustments"].append(result)

        for tid in task_ids:
            result = cls._recalculate_task(tid, is_addition, db)
            results["task_adjustments"].append(result)

        if project_ids or task_ids:
            logger.info(
                f"[Recalc] Holiday '{holiday.name}' ({action}): "
                f"{len(project_ids)} projects, {len(task_ids)} tasks adjusted"
            )

        return results

    @classmethod
    def identify_affected_projects(cls, holiday_date: date, db: Session) -> list[UUID]:
        rows = db.scalars(
            select(Project.id).where(
                Project.is_active == True,
                Project.planned_start_date <= holiday_date,
                Project.planned_end_date >= holiday_date,
            )
        ).all()
        return list(rows)

    @classmethod
    def identify_affected_tasks(
        cls, holiday_date: date, project_ids: list[UUID], db: Session
    ) -> list[UUID]:
        if not project_ids:
            return []
        rows = db.scalars(
            select(Task.id).where(
                Task.project_id.in_(project_ids),
                Task.is_active == True,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
                Task.planned_start_date <= holiday_date,
                Task.planned_end_date >= holiday_date,
            )
        ).all()
        return list(rows)

    @classmethod
    def _shift_end_date(cls, current_end: date, is_addition: bool, db: Session) -> date:
        """Shift end date by 1 working day.
        is_addition=True  → holiday added → end date moves LATER by 1 working day
        is_addition=False → holiday removed → end date moves EARLIER by 1 working day
        """
        direction = 1 if is_addition else -1
        candidate = current_end + timedelta(days=direction)
        while not WorkingDayEngine.is_working_day(candidate, db):
            candidate += timedelta(days=direction)
        return candidate

    @classmethod
    def _recalculate_project(
        cls, project_id: UUID, is_addition: bool, db: Session
    ) -> dict:
        project = db.get(Project, project_id)
        if not project or not project.planned_end_date:
            return {"project_id": str(project_id), "adjustment": 0}

        current_end = project.planned_end_date
        new_end = cls._shift_end_date(current_end, is_addition, db)

        if new_end == current_end:
            return {"project_id": str(project_id), "adjustment": 0}

        project.planned_end_date = new_end
        db.commit()

        from app.services.project_metrics_service import ProjectMetricsService
        ProjectMetricsService.recalculate(db, project_id)

        from app.services.audit_service import AuditService
        AuditService.log(
            db, "project", project_id, "AUTO_RECALC",
            old_value={"planned_end_date": current_end.isoformat()},
            new_value={"planned_end_date": new_end.isoformat()},
        )

        return {
            "project_id": str(project_id),
            "old_end": current_end.isoformat(),
            "new_end": new_end.isoformat(),
        }

    @classmethod
    def _recalculate_task(
        cls, task_id: UUID, is_addition: bool, db: Session
    ) -> dict:
        task = db.get(Task, task_id)
        if not task or not task.planned_end_date:
            return {"task_id": str(task_id), "adjustment": 0}

        current_end = task.planned_end_date
        new_end = cls._shift_end_date(current_end, is_addition, db)

        if new_end == current_end:
            return {"task_id": str(task_id), "adjustment": 0}

        task.planned_end_date = new_end
        db.commit()

        return {
            "task_id": str(task_id),
            "old_end": current_end.isoformat(),
            "new_end": new_end.isoformat(),
        }
