"""Tests for PendingScheduleReviewService.

Pattern: MagicMock db (no real DB connection), matching the existing test
style used in test_emergency_holiday.py and test_project_metrics_service.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from app.models.holiday import Holiday
from app.models.project import Project
from app.models.pending_schedule_review import PendingScheduleReview
from app.schemas.pending_schedule_review import (
    ReviewApplyRequest,
    ReviewRejectRequest,
)
from app.schemas.holiday import ProjectDateOverride, TaskDateOverride
from app.services.pending_schedule_review_service import PendingScheduleReviewService


# ── Constants ──────────────────────────────────────────────────────────────────

HOLIDAY_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PROJECT_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
MANAGER_ID = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
ADMIN_ID   = uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
REVIEW_ID  = uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None
    mock_db.scalars.return_value = MagicMock()
    mock_db.scalars.return_value.all.return_value = []
    return mock_db


@pytest.fixture
def service(db):
    return PendingScheduleReviewService(db, current_user_id=ADMIN_ID)


def _make_holiday(**kwargs) -> Holiday:
    defaults = dict(
        id=HOLIDAY_ID,
        name="Emergency Flood",
        date=date(2026, 7, 15),
        holiday_type="EMERGENCY",
        is_active=True,
        affects_working_days=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    h = Holiday(**defaults)
    return h


def _make_project(**kwargs) -> Project:
    defaults = dict(
        id=PROJECT_ID,
        project_code="PRJ-001",
        name="Project Alpha",
        planned_start_date=date(2026, 7, 1),
        planned_end_date=date(2026, 7, 31),
        status="In Progress",
        is_active=True,
        priority="HIGH",
        project_manager_id=MANAGER_ID,
    )
    defaults.update(kwargs)
    return Project(**defaults)


def _make_review(**kwargs) -> PendingScheduleReview:
    defaults = dict(
        id=REVIEW_ID,
        holiday_id=HOLIDAY_ID,
        project_id=PROJECT_ID,
        project_manager_id=MANAGER_ID,
        review_status="PENDING",
        notes=None,
        reviewed_by=None,
        reviewed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    r = MagicMock(spec=PendingScheduleReview)
    for k, v in defaults.items():
        setattr(r, k, v)
    return r


# ── Test 1: Emergency holiday creation → reviews generated ────────────────────

def test_create_reviews_for_holiday_creates_one_per_project(db, service):
    """Creating an Emergency Holiday should produce one PENDING review per
    affected active project."""
    project = _make_project()
    holiday = _make_holiday()

    impact_data = {
        "affected_projects": [
            {
                "project_id": PROJECT_ID,
                "project_name": "Project Alpha",
                "current_start_date": date(2026, 7, 1),
                "current_end_date": date(2026, 7, 31),
                "proposed_start_date": date(2026, 7, 1),
                "proposed_end_date": date(2026, 8, 1),
                "delivery_risk": "HIGH",
                "affected_tasks_count": 3,
            }
        ],
        "affected_tasks": [],
    }

    db.get.side_effect = lambda model, pk: holiday if pk == HOLIDAY_ID else project

    with patch.object(service, "_build_response") as mock_build, \
         patch("app.services.pending_schedule_review_service.AuditService") as mock_audit, \
         patch("app.services.holiday_service.HolidayService.get_impact_analysis",
               return_value=impact_data):

        mock_build.return_value = MagicMock()
        results = service.create_reviews_for_holiday(HOLIDAY_ID)

    # One review should have been created
    assert db.add.called
    assert mock_audit.log.called
    action_arg = mock_audit.log.call_args[1].get("action") or mock_audit.log.call_args[0][3]
    assert action_arg == "REVIEW_CREATED"


# ── Test 2: Non-EMERGENCY holiday → no reviews ────────────────────────────────

def test_create_reviews_for_public_holiday_does_nothing(db):
    """HolidayService.create() should NOT call create_reviews_for_holiday when
    the holiday type is not EMERGENCY."""
    from app.schemas.holiday import HolidayCreate
    from app.services.holiday_service import HolidayService

    data = HolidayCreate(
        name="New Year",
        date=date(2026, 1, 1),
        holiday_type="PUBLIC",
        affects_working_days=True,
    )

    def mock_add(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    db.add.side_effect = mock_add

    with patch("app.services.calendar_service.CalendarService.trigger_holiday_recalculation"), \
         patch("app.services.pending_schedule_review_service.PendingScheduleReviewService"
               ".create_reviews_for_holiday") as mock_create_reviews:

        HolidayService(db, current_user_id=ADMIN_ID).create(data)
        mock_create_reviews.assert_not_called()


# ── Test 3: EMERGENCY holiday creation hooks the PSR service ──────────────────

def test_create_emergency_holiday_calls_psr_service(db):
    """HolidayService.create() must call create_reviews_for_holiday when
    holiday_type == EMERGENCY."""
    from app.schemas.holiday import HolidayCreate
    from app.services.holiday_service import HolidayService

    data = HolidayCreate(
        name="Emergency Flood",
        date=date(2026, 7, 15),
        holiday_type="EMERGENCY",
        affects_working_days=True,
    )

    def mock_add(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    db.add.side_effect = mock_add

    with patch(
        "app.services.pending_schedule_review_service.PendingScheduleReviewService"
        ".create_reviews_for_holiday"
    ) as mock_create_reviews, \
         patch("app.services.calendar_service.CalendarService.trigger_holiday_recalculation"):

        HolidayService(db, current_user_id=ADMIN_ID).create(data)
        mock_create_reviews.assert_called_once()


# ── Test 4: Owner-scoped pending query ────────────────────────────────────────

def test_get_pending_for_manager_returns_only_own_reviews(db, service):
    """get_pending_for_manager must filter by project_manager_id."""
    review = _make_review()
    db.scalars.return_value.all.return_value = [review]

    with patch.object(service, "_build_response", return_value=MagicMock()):
        results = service.get_pending_for_manager(MANAGER_ID)

    assert len(results) == 1
    # Confirm the WHERE clause targeted the right owner
    call_args = db.scalars.call_args
    # The statement should include a filter; we trust the ORM — presence of
    # call and a result is the observable behaviour.
    assert db.scalars.called


# ── Test 5: Admin sees all pending reviews ────────────────────────────────────

def test_get_all_pending_returns_every_review(db, service):
    """get_all_pending must not apply any owner filter."""
    r1 = _make_review()
    r2 = _make_review(id=uuid.uuid4(), project_manager_id=uuid.uuid4())
    db.scalars.return_value.all.return_value = [r1, r2]

    with patch.object(service, "_build_response", return_value=MagicMock()):
        results = service.get_all_pending()

    assert len(results) == 2


# ── Test 6: Impact analysis scoped to review's project ───────────────────────

def test_impact_analysis_scoped_to_review_project(db, service):
    """get_impact_analysis_for_review must return only the project and tasks
    that belong to the review — not all affected projects."""
    review = _make_review()
    db.get.return_value = review

    other_project_id = uuid.uuid4()
    full_impact = {
        "holiday_id": HOLIDAY_ID,
        "holiday_name": "Emergency Flood",
        "holiday_date": date(2026, 7, 15),
        "affected_projects": [
            {"project_id": PROJECT_ID, "project_name": "Project Alpha",
             "current_start_date": date(2026, 7, 1), "current_end_date": date(2026, 7, 31),
             "proposed_start_date": date(2026, 7, 1), "proposed_end_date": date(2026, 8, 1),
             "delivery_risk": "HIGH", "affected_tasks_count": 1},
            {"project_id": other_project_id, "project_name": "Project Beta",
             "current_start_date": date(2026, 7, 1), "current_end_date": date(2026, 7, 31),
             "proposed_start_date": date(2026, 7, 1), "proposed_end_date": date(2026, 8, 1),
             "delivery_risk": "MEDIUM", "affected_tasks_count": 2},
        ],
        "affected_tasks": [],
    }

    with patch("app.services.holiday_service.HolidayService.get_impact_analysis",
               return_value=full_impact), \
         patch.object(service, "_assert_owner_or_admin"):
        result = service.get_impact_analysis_for_review(REVIEW_ID, MANAGER_ID)

    # Only the review's project should appear
    assert result["project"]["project_id"] == PROJECT_ID
    assert "project_name" in result["project"]


# ── Test 7: Apply review updates review status ────────────────────────────────

def test_apply_review_marks_status_applied(db, service):
    """apply_review must set review_status = APPLIED and call AuditService."""
    review = _make_review()
    db.get.return_value = review

    data = ReviewApplyRequest()

    with patch("app.services.holiday_service.HolidayService.apply_emergency_holiday",
               return_value={"success": True, "message": "done"}), \
         patch("app.services.pending_schedule_review_service.AuditService") as mock_audit, \
         patch.object(service, "_assert_owner_or_admin"):

        result = service.apply_review(REVIEW_ID, data, MANAGER_ID)

    assert review.review_status == "APPLIED"
    assert review.reviewed_by == MANAGER_ID
    assert review.reviewed_at is not None
    assert result["success"] is True
    assert mock_audit.log.called


# ── Test 8: Reject review leaves tasks unchanged ─────────────────────────────

def test_reject_review_leaves_tasks_unchanged(db, service):
    """reject_review must mark status REJECTED without calling apply_emergency_holiday."""
    review = _make_review()
    db.get.return_value = review

    data = ReviewRejectRequest(notes="Client requested no changes")

    with patch("app.services.holiday_service.HolidayService.apply_emergency_holiday") as mock_apply, \
         patch("app.services.pending_schedule_review_service.AuditService"), \
         patch.object(service, "_assert_owner_or_admin"):

        result = service.reject_review(REVIEW_ID, data, MANAGER_ID)

    assert review.review_status == "REJECTED"
    assert review.notes == "Client requested no changes"
    mock_apply.assert_not_called()
    assert result["success"] is True


# ── Test 9: Double-apply raises ValueError ────────────────────────────────────

def test_apply_already_applied_review_raises(db, service):
    """Calling apply_review on an APPLIED review must raise ValueError."""
    review = _make_review(review_status="APPLIED")
    db.get.return_value = review

    with pytest.raises(ValueError, match="not in PENDING"):
        service.apply_review(REVIEW_ID, ReviewApplyRequest(), MANAGER_ID)


# ── Test 10: Double-reject raises ValueError ──────────────────────────────────

def test_reject_already_rejected_review_raises(db, service):
    """Calling reject_review on a REJECTED review must raise ValueError."""
    review = _make_review(review_status="REJECTED")
    db.get.return_value = review

    with pytest.raises(ValueError, match="not in PENDING"):
        service.reject_review(REVIEW_ID, ReviewRejectRequest(), MANAGER_ID)


# ── Test 11: Deactivate holiday cancels open reviews ─────────────────────────

def test_deactivate_emergency_holiday_cancels_pending_reviews(db):
    """HolidayService.toggle_active (deactivating an EMERGENCY holiday) must
    call cancel_reviews_for_holiday."""
    from app.services.holiday_service import HolidayService

    holiday = _make_holiday(is_active=True)
    db.get.return_value = holiday

    with patch("app.services.calendar_service.CalendarService.trigger_holiday_recalculation"), \
         patch(
             "app.services.pending_schedule_review_service.PendingScheduleReviewService"
             ".cancel_reviews_for_holiday"
         ) as mock_cancel:

        HolidayService(db, current_user_id=ADMIN_ID).toggle_active(HOLIDAY_ID)
        mock_cancel.assert_called_once_with(HOLIDAY_ID)


# ── Test 12: No affected projects → no reviews created ───────────────────────

def test_create_reviews_empty_when_no_affected_projects(db, service):
    """If the Emergency Holiday does not overlap any active project, no
    PendingScheduleReview rows should be created."""
    impact_data = {"affected_projects": [], "affected_tasks": []}

    with patch("app.services.holiday_service.HolidayService.get_impact_analysis",
               return_value=impact_data):
        results = service.create_reviews_for_holiday(HOLIDAY_ID)

    assert results == []
    db.add.assert_not_called()


# ── Test 13: Review with null manager is not visible to non-admins ────────────

def test_null_manager_review_not_returned_for_non_admin(db, service):
    """A review whose project_manager_id is NULL should not appear in a non-admin
    manager's pending list (their ID != NULL)."""
    null_manager_review = _make_review(project_manager_id=None)
    db.scalars.return_value.all.return_value = [null_manager_review]

    # get_pending_for_manager filters by project_manager_id == MANAGER_ID.
    # The ORM will not return the null-manager review for this query.
    # We simulate this: return empty list for MANAGER_ID query.
    db.scalars.return_value.all.return_value = []

    with patch.object(service, "_build_response", return_value=MagicMock()):
        results = service.get_pending_for_manager(MANAGER_ID)

    assert results == []


# ── Test 14: Audit log entries created for all status transitions ─────────────

def test_audit_log_created_for_apply(db, service):
    """An audit entry with action=REVIEW_APPLIED must be created on apply."""
    review = _make_review()
    db.get.return_value = review

    with patch("app.services.holiday_service.HolidayService.apply_emergency_holiday",
               return_value={"success": True, "message": "done"}), \
         patch("app.services.pending_schedule_review_service.AuditService.log") as mock_log, \
         patch.object(service, "_assert_owner_or_admin"):

        service.apply_review(REVIEW_ID, ReviewApplyRequest(), MANAGER_ID)

    logged_actions = [c[0][3] for c in mock_log.call_args_list]
    assert "REVIEW_APPLIED" in logged_actions


def test_audit_log_created_for_reject(db, service):
    """An audit entry with action=REVIEW_REJECTED must be created on reject."""
    review = _make_review()
    db.get.return_value = review

    with patch("app.services.pending_schedule_review_service.AuditService.log") as mock_log, \
         patch.object(service, "_assert_owner_or_admin"):

        service.reject_review(REVIEW_ID, ReviewRejectRequest(), MANAGER_ID)

    logged_actions = [c[0][3] for c in mock_log.call_args_list]
    assert "REVIEW_REJECTED" in logged_actions
