from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.pending_schedule_review import PendingScheduleReview
from app.models.project import Project
from app.models.holiday import Holiday
from app.schemas.dashboard_widget import PendingScheduleReviewWidget
from app.schemas.pending_schedule_review import (
    PendingScheduleReviewResponse,
    ReviewApplyRequest,
    ReviewRejectRequest,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# RBAC codes that are treated as super-admin for ownership bypass
_SUPER_ADMIN_CODES = {"ADMIN", "CEO", "CHIEF_EXECUTIVE_OFFICER", "ADMINISTRATOR"}


class PendingScheduleReviewService:
    """Orchestrates the Emergency Holiday → Pending Schedule Review lifecycle.

    This service does NOT replace or redesign any existing service.  It wires
    together HolidayService (for impact analysis and applying shifts),
    ProjectMetricsService (for recalculation after apply), and AuditService
    (for the audit trail) by delegating to each.
    """

    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_admin(self, user_id: uuid.UUID) -> bool:
        """Return True if the user holds a super-admin role code."""
        from app.models.employee_role import EmployeeRole
        from app.models.role import Role

        stmt = (
            select(Role.role_code)
            .join(EmployeeRole, EmployeeRole.role_id == Role.id)
            .where(
                EmployeeRole.employee_id == user_id,
                EmployeeRole.is_active == True,
                Role.is_active == True,
            )
        )
        codes = [row[0] for row in self.db.execute(stmt).all()]
        return any(c in _SUPER_ADMIN_CODES for c in codes)

    def _assert_owner_or_admin(
        self, review: PendingScheduleReview, requester_id: uuid.UUID
    ) -> None:
        """Raise PermissionError if requester is neither the project manager
        nor an admin."""
        if review.project_manager_id == requester_id:
            return
        if self._is_admin(requester_id):
            return
        raise PermissionError(
            "You are not authorized to act on this schedule review."
        )

    def _build_response(self, review: PendingScheduleReview) -> PendingScheduleReviewResponse:
        """Enrich the ORM object with holiday/project names for the response."""
        from app.models.employee import Employee

        holiday = self.db.get(Holiday, review.holiday_id)
        project = self.db.get(Project, review.project_id)

        manager_name = None
        if review.project_manager_id:
            mgr = self.db.get(Employee, review.project_manager_id)
            if mgr:
                manager_name = f"{mgr.first_name} {mgr.last_name or ''}".strip()

        return PendingScheduleReviewResponse(
            id=review.id,
            holiday_id=review.holiday_id,
            holiday_name=holiday.name if holiday else "",
            holiday_date=holiday.date if holiday else None,
            project_id=review.project_id,
            project_name=project.name if project else "",
            project_code=project.project_code if project else "",
            project_manager_id=review.project_manager_id,
            project_manager_name=manager_name,
            review_status=review.review_status,
            notes=review.notes,
            reviewed_by=review.reviewed_by,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            updated_at=review.updated_at,
        )

    # ── Public methods ────────────────────────────────────────────────────────

    def create_reviews_for_holiday(
        self, holiday_id: uuid.UUID
    ) -> list[PendingScheduleReviewResponse]:
        """Generate one PendingScheduleReview per affected active project.

        Called automatically from HolidayService.create() when the holiday
        type is EMERGENCY.  The method is idempotent: if a review already
        exists for a (holiday_id, project_id) pair it logs a warning and skips
        rather than raising.

        Returns the list of created review objects.
        """
        from app.services.holiday_service import HolidayService

        impact = HolidayService(self.db, self.current_user_id).get_impact_analysis(
            holiday_id
        )

        created: list[tuple] = []

        for proj_impact in impact.get("affected_projects", []):
            project_id = proj_impact["project_id"]

            # Resolve the project manager at creation time
            project = self.db.get(Project, project_id)
            if not project:
                logger.warning(
                    "[PSR] Project %s not found during review creation — skipping",
                    project_id,
                )
                continue

            manager_id = project.project_manager_id  # may be None

            review = PendingScheduleReview(
                holiday_id=holiday_id,
                project_id=project_id,
                project_manager_id=manager_id,
                review_status="PENDING",
            )
            self.db.add(review)
            try:
                savepoint = self.db.begin_nested()  # Create savepoint for this iteration
                self.db.flush()  # catch IntegrityError before committing
                savepoint.commit()
            except IntegrityError:
                savepoint.rollback()  # Only rolls back THIS iteration, not prior flushes
                logger.warning(
                    "[PSR] Duplicate review skipped for holiday=%s project=%s",
                    holiday_id,
                    project_id,
                )
                continue

            created.append((review, project_id, manager_id))

        # Single commit AFTER the entire loop — all reviews committed atomically
        self.db.commit()

        result: list[PendingScheduleReviewResponse] = []
        for review, project_id, manager_id in created:
            self.db.refresh(review)
            AuditService.log(
                self.db,
                "pending_schedule_review",
                review.id,
                "REVIEW_CREATED",
                performed_by=self.current_user_id,
                new_value={
                    "holiday_id": str(holiday_id),
                    "project_id": str(project_id),
                    "project_manager_id": str(manager_id) if manager_id else None,
                },
            )
            result.append(self._build_response(review))

        return result

    def get_pending_for_manager(
        self, manager_id: uuid.UUID
    ) -> list[PendingScheduleReviewResponse]:
        """Return all PENDING reviews assigned to this project manager.

        Uses the ix_psr_manager_status composite index — O(rows owned by user),
        not O(all reviews).
        """
        reviews = self.db.scalars(
            select(PendingScheduleReview)
            .options(
                joinedload(PendingScheduleReview.project),
                joinedload(PendingScheduleReview.holiday),
                joinedload(PendingScheduleReview.project_manager),
            )
            .where(
                PendingScheduleReview.project_manager_id == manager_id,
                PendingScheduleReview.review_status == "PENDING",
            )
            .order_by(PendingScheduleReview.created_at.desc())
        ).all()
        return [self._build_response(r) for r in reviews]

    def get_all_pending(self) -> list[PendingScheduleReviewResponse]:
        """Return all PENDING reviews regardless of owner (Admin use)."""
        reviews = self.db.scalars(
            select(PendingScheduleReview).where(
                PendingScheduleReview.review_status == "PENDING"
            )
        ).all()
        return [self._build_response(r) for r in reviews]

    def get_all_for_manager(
        self, manager_id: uuid.UUID
    ) -> list[PendingScheduleReviewResponse]:
        """Return ALL reviews (any status) for a given manager — useful for
        history/audit views."""
        reviews = self.db.scalars(
            select(PendingScheduleReview).where(
                PendingScheduleReview.project_manager_id == manager_id,
            )
        ).all()
        return [self._build_response(r) for r in reviews]

    def get_by_id(
        self, review_id: uuid.UUID, requester_id: uuid.UUID | None = None
    ) -> PendingScheduleReviewResponse:
        """Fetch a single review.  If requester_id is provided the ownership
        check is enforced (project manager or admin only)."""
        review = self.db.get(PendingScheduleReview, review_id)
        if not review:
            raise ValueError(f"Schedule review {review_id} not found")
        if requester_id:
            self._assert_owner_or_admin(review, requester_id)
        return self._build_response(review)

    def get_impact_analysis_for_review(
        self, review_id: uuid.UUID, requester_id: uuid.UUID
    ) -> dict:
        """Return the impact analysis scoped to the review's single project.

        Delegates to HolidayService.get_impact_analysis() and then filters
        the result down to tasks that belong to this review's project only.
        """
        from app.services.holiday_service import HolidayService

        review = self.db.get(PendingScheduleReview, review_id)
        if not review:
            raise ValueError(f"Schedule review {review_id} not found")

        self._assert_owner_or_admin(review, requester_id)

        full_impact = HolidayService(
            self.db, requester_id
        ).get_impact_analysis(review.holiday_id)

        # Filter to the project that this review covers
        project_impacts = [
            p
            for p in full_impact.get("affected_projects", [])
            if p["project_id"] == review.project_id
        ]
        task_impacts = [
            t
            for t in full_impact.get("affected_tasks", [])
            if t.get("project_id") == str(review.project_id)
        ]

        return {
            "review_id": review.id,
            "review_status": review.review_status,
            "holiday_id": full_impact["holiday_id"],
            "holiday_name": full_impact["holiday_name"],
            "holiday_date": full_impact["holiday_date"],
            "project": project_impacts[0] if project_impacts else None,
            "affected_tasks": task_impacts,
        }

    def apply_review(
        self,
        review_id: uuid.UUID,
        data: ReviewApplyRequest,
        requester_id: uuid.UUID,
    ) -> dict:
        """Apply the proposed schedule changes and mark the review as APPLIED.

        Delegates the actual task/project date updates and project metrics
        recalculation to the existing HolidayService.apply_emergency_holiday().
        """
        from app.services.holiday_service import HolidayService
        from app.schemas.holiday import EmergencyHolidayApplyRequest

        review = self.db.get(PendingScheduleReview, review_id)
        if not review:
            raise ValueError(f"Schedule review {review_id} not found")

        self._assert_owner_or_admin(review, requester_id)

        if review.review_status != "PENDING":
            raise ValueError(
                f"Review is not in PENDING status (current: {review.review_status}). "
                "Only PENDING reviews can be applied."
            )

        # Delegate to the existing apply logic — re-using all its validations
        apply_request = EmergencyHolidayApplyRequest(
            project_updates=data.project_updates,
            task_updates=data.task_updates,
        )
        HolidayService(self.db, requester_id).apply_emergency_holiday(
            review.holiday_id, apply_request
        )

        # Mark the review as resolved
        now = datetime.now(timezone.utc)
        review.review_status = "APPLIED"
        review.reviewed_by = requester_id
        review.reviewed_at = now
        self.db.commit()
        self.db.refresh(review)

        AuditService.log(
            self.db,
            "pending_schedule_review",
            review.id,
            "REVIEW_APPLIED",
            performed_by=requester_id,
            new_value={
                "review_id": str(review_id),
                "applied_by": str(requester_id),
                "applied_at": now.isoformat(),
            },
        )

        return {
            "success": True,
            "message": "Schedule review applied. Tasks and project dates have been updated.",
        }

    def reject_review(
        self,
        review_id: uuid.UUID,
        data: ReviewRejectRequest,
        requester_id: uuid.UUID,
    ) -> dict:
        """Reject the proposed schedule — no task or project dates are changed."""
        review = self.db.get(PendingScheduleReview, review_id)
        if not review:
            raise ValueError(f"Schedule review {review_id} not found")

        self._assert_owner_or_admin(review, requester_id)

        if review.review_status != "PENDING":
            raise ValueError(
                f"Review is not in PENDING status (current: {review.review_status}). "
                "Only PENDING reviews can be rejected."
            )

        now = datetime.now(timezone.utc)
        review.review_status = "REJECTED"
        review.reviewed_by = requester_id
        review.reviewed_at = now
        review.notes = data.notes
        self.db.commit()
        self.db.refresh(review)

        AuditService.log(
            self.db,
            "pending_schedule_review",
            review.id,
            "REVIEW_REJECTED",
            performed_by=requester_id,
            new_value={
                "review_id": str(review_id),
                "rejected_by": str(requester_id),
                "rejected_at": now.isoformat(),
                "notes": data.notes,
            },
        )

        return {
            "success": True,
            "message": "Schedule review rejected. Existing schedules remain unchanged.",
        }

    def cancel_reviews_for_holiday(self, holiday_id: uuid.UUID) -> int:
        """Cancel all PENDING reviews for a holiday (called when a holiday is
        deactivated via toggle_active).

        Returns the count of reviews that were cancelled.
        """
        pending_reviews = self.db.scalars(
            select(PendingScheduleReview).where(
                PendingScheduleReview.holiday_id == holiday_id,
                PendingScheduleReview.review_status == "PENDING",
            )
        ).all()

        now = datetime.now(timezone.utc)
        count = 0
        for review in pending_reviews:
            review.review_status = "REJECTED"
            review.reviewed_by = self.current_user_id
            review.reviewed_at = now
            review.notes = "Auto-cancelled: Emergency Holiday was deactivated."
            count += 1

        if count:
            self.db.commit()
            AuditService.log(
                self.db,
                "pending_schedule_review",
                holiday_id,  # entity_id = the holiday for this batch event
                "REVIEWS_CANCELLED",
                performed_by=self.current_user_id,
                new_value={
                    "holiday_id": str(holiday_id),
                    "cancelled_count": count,
                    "reason": "Emergency Holiday deactivated",
                },
            )
            logger.info(
                "[PSR] Cancelled %d pending review(s) for holiday %s",
                count,
                holiday_id,
            )

        return count

    # ── Dashboard helpers ─────────────────────────────────────────────────────

    def get_widget_data_for_manager(
        self, manager_id: uuid.UUID
    ) -> list[PendingScheduleReviewWidget]:
        """Return the widget-shaped pending reviews for a project manager.

        Only returns PENDING reviews — resolved reviews are excluded from the
        widget (they still appear in audit logs and history queries).
        """
        reviews = self.db.scalars(
            select(PendingScheduleReview).where(
                PendingScheduleReview.project_manager_id == manager_id,
                PendingScheduleReview.review_status == "PENDING",
            )
        ).all()
        return self._to_widgets(reviews)

    def get_widget_data_all(self) -> list[PendingScheduleReviewWidget]:
        """Return widget-shaped PENDING reviews for all owners (Admin view)."""
        reviews = self.db.scalars(
            select(PendingScheduleReview).where(
                PendingScheduleReview.review_status == "PENDING"
            )
        ).all()
        return self._to_widgets(reviews)

    def _to_widgets(
        self, reviews: list[PendingScheduleReview]
    ) -> list[PendingScheduleReviewWidget]:
        from app.models.employee import Employee

        widgets: list[PendingScheduleReviewWidget] = []
        for review in reviews:
            holiday = self.db.get(Holiday, review.holiday_id)
            project = self.db.get(Project, review.project_id)
            if not holiday or not project:
                continue

            manager_name = None
            if review.project_manager_id:
                mgr = self.db.get(Employee, review.project_manager_id)
                if mgr:
                    manager_name = f"{mgr.first_name} {mgr.last_name or ''}".strip()

            widgets.append(
                PendingScheduleReviewWidget(
                    id=review.id,
                    holiday_id=review.holiday_id,
                    holiday_name=holiday.name,
                    holiday_date=holiday.date,
                    project_id=review.project_id,
                    project_name=project.name,
                    project_code=project.project_code,
                    project_manager_name=manager_name,
                    review_status=review.review_status,
                    created_at=review.created_at,
                )
            )
        return widgets
