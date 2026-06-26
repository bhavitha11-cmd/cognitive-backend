from datetime import date
import uuid
from typing import Any, Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from app.models.idle_reason_master import IdleReasonMaster
from app.models.idle_classification import IdleClassification
from app.services.audit_service import AuditService


class IdleAnalyzer:
    @staticmethod
    def get_active_reasons(
        db: Session,
        department_id: uuid.UUID | None = None
    ) -> list[IdleReasonMaster]:
        """Fetch active idle reasons, optionally filtered by department or global/unassigned."""
        query = select(IdleReasonMaster).where(IdleReasonMaster.is_active == True)
        if department_id:
            query = query.where(
                or_(
                    IdleReasonMaster.department_id == department_id,
                    IdleReasonMaster.department_id.is_(None)
                )
            )
        else:
            query = query.where(IdleReasonMaster.department_id.is_(None))

        return db.scalars(query.order_by(IdleReasonMaster.display_order)).all()

    @staticmethod
    def classify_idle_segment(
        db: Session,
        employee_id: uuid.UUID,
        query_date: date,
        idle_segment_identifier: str,
        reason_id: uuid.UUID,
        remarks: str | None = None,
        performed_by_id: uuid.UUID | None = None
    ) -> IdleClassification:
        """Create or update the classification tag for a dynamic idle segment."""
        # 1. Validate reason exists
        reason = db.get(IdleReasonMaster, reason_id)
        if not reason or not reason.is_active:
            raise ValueError(f"Active idle reason with id {reason_id} not found.")

        # 2. Check for existing classification
        existing = db.scalar(
            select(IdleClassification).where(
                IdleClassification.employee_id == employee_id,
                IdleClassification.date == query_date,
                IdleClassification.idle_segment_identifier == idle_segment_identifier,
            )
        )

        old_values = {}
        if existing:
            old_values = {
                "reason_id": str(existing.reason_id),
                "remarks": existing.remarks,
            }
            existing.reason_id = reason_id
            existing.remarks = remarks
            record = existing
        else:
            record = IdleClassification(
                employee_id=employee_id,
                date=query_date,
                idle_segment_identifier=idle_segment_identifier,
                reason_id=reason_id,
                remarks=remarks,
            )
            db.add(record)

        try:
            db.flush()
            db.commit()
            db.refresh(record)

            AuditService.log(
                db,
                "idle_classification",
                record.id,
                "UPDATE" if existing else "CREATE",
                performed_by=performed_by_id,
                old_value=old_values if existing else None,
                new_value={
                    "employee_id": str(employee_id),
                    "date": str(query_date),
                    "idle_segment_identifier": idle_segment_identifier,
                    "reason_id": str(reason_id),
                    "remarks": remarks,
                },
            )
        except Exception:
            db.rollback()
            raise

        return record
