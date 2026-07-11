from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.parent_project import ParentProject
from app.models.project import Project
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class ParentProjectMetricsService:
    @classmethod
    def recalculate(cls, db: Session, parent_project_id: UUID) -> dict[str, Any]:
        """
        Recalculates rolled-up metrics for a ParentProject based on its Parts (Project rows).
        Persists results in a single database update.
        """
        parent_project = db.get(ParentProject, parent_project_id)
        if not parent_project or not parent_project.is_active:
            return {}

        # 1. Load active parts (Project model represents Parts)
        parts = db.scalars(
            select(Project).where(
                and_(
                    Project.parent_project_id == parent_project_id,
                    Project.is_active == True  # noqa: E712
                )
            )
        ).all()

        # 2. Calculate values
        part_count = len(parts)

        # Status priority rule derivation
        status_set = {p.status for p in parts}
        if not parts:
            status = "Yet To Start"
        elif "In Progress" in status_set:
            status = "In Progress"
        elif "On Hold" in status_set:
            status = "On Hold"
        elif all(p.status in {"Completed", "Cancelled"} for p in parts):
            if any(p.status == "Completed" for p in parts):
                status = "Completed"
            else:
                status = "Cancelled"
        else:
            status = "Yet To Start"

        # Hours
        estimated_hours = round(sum(float(p.estimated_hours or 0.0) for p in parts), 2)
        actual_hours = round(sum(float(p.actual_hours or 0.0) for p in parts), 2)

        # Dates
        planned_start_dates = [p.planned_start_date for p in parts if p.planned_start_date]
        planned_end_dates = [p.planned_end_date for p in parts if p.planned_end_date]
        actual_start_dates = [p.actual_start_date for p in parts if p.actual_start_date]
        actual_end_dates = [p.actual_end_date for p in parts if p.actual_end_date]

        planned_start_date = min(planned_start_dates) if planned_start_dates else None
        planned_end_date = max(planned_end_dates) if planned_end_dates else None
        actual_start_date = min(actual_start_dates) if actual_start_dates else None

        all_parts_closed = parts and all(p.status in {"Completed", "Cancelled"} for p in parts)
        actual_end_date = max(actual_end_dates) if (all_parts_closed and actual_end_dates) else None

        # Hour-weighted progress
        total_est_hours = sum(float(p.estimated_hours or 0.0) for p in parts)
        if total_est_hours > 0:
            progress = round(
                sum(float(p.progress or 0.0) * float(p.estimated_hours or 0.0) for p in parts) / total_est_hours,
                2
            )
        else:
            progress = round(sum(float(p.progress or 0.0) for p in parts) / part_count, 2) if part_count > 0 else 0.0

        # Capture old values for auditing
        old_values = {
            "status": parent_project.status,
            "progress": float(parent_project.progress or 0.0),
            "planned_start_date": str(parent_project.planned_start_date) if parent_project.planned_start_date else None,
            "planned_end_date": str(parent_project.planned_end_date) if parent_project.planned_end_date else None,
            "actual_start_date": str(parent_project.actual_start_date) if parent_project.actual_start_date else None,
            "actual_end_date": str(parent_project.actual_end_date) if parent_project.actual_end_date else None,
            "estimated_hours": float(parent_project.estimated_hours or 0.0),
            "actual_hours": float(parent_project.actual_hours or 0.0),
        }

        new_values = {
            "status": status,
            "progress": float(progress),
            "planned_start_date": str(planned_start_date) if planned_start_date else None,
            "planned_end_date": str(planned_end_date) if planned_end_date else None,
            "actual_start_date": str(actual_start_date) if actual_start_date else None,
            "actual_end_date": str(actual_end_date) if actual_end_date else None,
            "estimated_hours": float(estimated_hours),
            "actual_hours": float(actual_hours),
        }

        # Update values
        parent_project.status = status
        parent_project.progress = progress
        parent_project.planned_start_date = planned_start_date
        parent_project.planned_end_date = planned_end_date
        parent_project.actual_start_date = actual_start_date
        parent_project.actual_end_date = actual_end_date
        parent_project.estimated_hours = estimated_hours
        parent_project.actual_hours = actual_hours

        db.flush()

        # Audit log if changed
        changed = {k: v for k, v in new_values.items() if str(v) != str(old_values.get(k))}
        if changed:
            try:
                AuditService.log(
                    db,
                    "parent_project",
                    parent_project_id,
                    "AUTO_RECALC",
                    performed_by=None,
                    old_value={k: old_values[k] for k in changed},
                    new_value={k: new_values[k] for k in changed},
                )
            except Exception:
                logger.warning(
                    "[ParentProjectMetrics] Audit log failed for parent project %s — skipping.",
                    parent_project_id, exc_info=True,
                )

        return {"old": old_values, "new": new_values}
