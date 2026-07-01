from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.pending_schedule_review import ReviewApplyRequest, ReviewRejectRequest

router = APIRouter(
    prefix="/schedule-reviews",
    tags=["Schedule Reviews"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.pending_schedule_review_service import PendingScheduleReviewService

    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity",
        )
    return PendingScheduleReviewService(db, current_user_id=uid)


def _get_requester_uuid(current_user_id: str = Depends(get_current_user)) -> uuid.UUID:
    try:
        return uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=APIResponse,
    summary="Get pending schedule reviews for the current user",
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def list_pending_reviews(service=Depends(_get_service)):
    """Return all PENDING schedule reviews assigned to the logged-in project
    manager.  Admins with full data-access receive all pending reviews across
    all project managers.

    Resolved reviews (APPLIED or REJECTED) are excluded — they remain
    available in the audit log.
    """
    # Delegate to the service — it handles the RBAC data-access level internally
    # by inspecting the current_user_id that was injected at construction time.
    # We call get_pending_for_manager here; the dashboard widget endpoint uses
    # the widget-shaped variant.  Admins can call get_all_pending() directly.
    if service.current_user_id and service._is_admin(service.current_user_id):
        reviews = service.get_all_pending()
    else:
        reviews = service.get_pending_for_manager(service.current_user_id)

    return APIResponse(
        success=True,
        message="Pending schedule reviews retrieved",
        data={
            "reviews": [r.model_dump(mode="json") for r in reviews],
            "count": len(reviews),
        },
    )


@router.get(
    "/history",
    response_model=APIResponse,
    summary="Get all schedule reviews (any status) for the current user",
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def list_review_history(
    service=Depends(_get_service),
    requester_id: uuid.UUID = Depends(_get_requester_uuid),
):
    """Return all reviews (PENDING, APPLIED, REJECTED) for the current project
    manager — useful for historical / audit review.  Admins receive all reviews
    across all project managers."""
    if service._is_admin(requester_id):
        # Admin: return everything for context
        from sqlalchemy import select
        from app.models.pending_schedule_review import PendingScheduleReview

        all_reviews = service.db.scalars(select(PendingScheduleReview)).all()
        responses = [service._build_response(r) for r in all_reviews]
    else:
        responses = service.get_all_for_manager(requester_id)

    return APIResponse(
        success=True,
        message="Review history retrieved",
        data={
            "reviews": [r.model_dump(mode="json") for r in responses],
            "count": len(responses),
        },
    )


@router.get(
    "/{id}/impact-analysis",
    response_model=APIResponse,
    summary="Get impact analysis for a pending schedule review",
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def get_impact_analysis(
    id: uuid.UUID,
    service=Depends(_get_service),
    requester_id: uuid.UUID = Depends(_get_requester_uuid),
):
    """Return the Emergency Holiday impact analysis scoped to the single
    project covered by this review.

    Only the assigned project manager (or an Admin) may access this endpoint.
    The returned data includes the proposed new dates for the project and each
    of its affected tasks — the project manager uses this to decide whether to
    apply or reject the proposed changes.
    """
    try:
        impact = service.get_impact_analysis_for_review(id, requester_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))

    return APIResponse(
        success=True,
        message="Impact analysis retrieved",
        data=impact,
    )


@router.post(
    "/{id}/apply",
    response_model=APIResponse,
    summary="Apply the proposed schedule for this review",
    dependencies=[Depends(require_permission("Projects", "edit"))],
)
def apply_review(
    id: uuid.UUID,
    data: ReviewApplyRequest,
    service=Depends(_get_service),
    requester_id: uuid.UUID = Depends(_get_requester_uuid),
):
    """Accept the proposed schedule changes.

    The project manager may supply custom date overrides in
    ``project_updates`` and ``task_updates``.  If no overrides are provided
    the system-computed proposal from the impact analysis is applied as-is.

    After applying:
    - Task and project planned dates are updated.
    - Project metrics are recalculated.
    - The review is marked **APPLIED** and disappears from the pending list.
    - An audit entry is recorded.

    Only the assigned project manager (or an Admin) may call this endpoint.
    """
    try:
        result = service.apply_review(id, data, requester_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))

    return APIResponse(success=True, message=result["message"])


@router.post(
    "/{id}/reject",
    response_model=APIResponse,
    summary="Reject the proposed schedule for this review",
    dependencies=[Depends(require_permission("Projects", "edit"))],
)
def reject_review(
    id: uuid.UUID,
    data: ReviewRejectRequest,
    service=Depends(_get_service),
    requester_id: uuid.UUID = Depends(_get_requester_uuid),
):
    """Keep the existing schedule — no task or project dates are changed.

    After rejecting:
    - No task or project dates are modified.
    - The review is marked **REJECTED** and disappears from the pending list.
    - The optional ``notes`` field is saved for audit purposes.
    - An audit entry is recorded.

    Only the assigned project manager (or an Admin) may call this endpoint.
    """
    try:
        result = service.reject_review(id, data, requester_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))

    return APIResponse(success=True, message=result["message"])
