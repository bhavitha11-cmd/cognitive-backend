from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import MagicMock, patch
import pytest

from app.models.holiday import Holiday
from app.models.project import Project
from app.models.task import Task
from app.schemas.holiday import HolidayCreate, EmergencyHolidayApplyRequest, ProjectDateOverride, TaskDateOverride
from app.services.holiday_service import HolidayService


@pytest.fixture
def db():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None
    mock_db.scalars.return_value = MagicMock()
    mock_db.scalars.return_value.all.return_value = []
    mock_db.scalars.return_value.first.return_value = None
    return mock_db


@pytest.fixture
def service(db):
    return HolidayService(db, current_user_id=uuid.uuid4())


def test_create_emergency_holiday_skips_recalculation(db, service):
    data = HolidayCreate(
        name="Emergency Flood",
        date=date(2026, 7, 1),
        holiday_type="EMERGENCY",
        description="Severe flooding forecast",
        affects_working_days=True
    )
    
    def mock_add(holiday):
        holiday.id = uuid.uuid4()
        holiday.created_at = datetime.now()
        holiday.updated_at = datetime.now()
        
    db.add.side_effect = mock_add

    with patch("app.services.calendar_service.CalendarService.trigger_holiday_recalculation") as mock_recalc, \
         patch(
             "app.services.pending_schedule_review_service.PendingScheduleReviewService"
             ".create_reviews_for_holiday"
         ):
        res = service.create(data)
        assert res.name == "Emergency Flood"
        assert res.holiday_type == "EMERGENCY"
        # Calendar recalculation must NOT be called for EMERGENCY holidays —
        # the PSR queue is used instead.
        mock_recalc.assert_not_called()


def test_get_impact_analysis(db, service):
    holiday_id = uuid.uuid4()
    holiday = Holiday(
        id=holiday_id,
        name="Emergency Storm",
        date=date(2026, 7, 1),
        holiday_type="EMERGENCY",
        is_active=True
    )
    db.get.return_value = holiday

    proj = Project(
        id=uuid.uuid4(),
        project_code="PRJ-001",
        name="Aerospace wing design",
        planned_start_date=date(2026, 6, 25),
        planned_end_date=date(2026, 7, 5),
        priority="HIGH",
        is_active=True,
        status="IN_PROGRESS"
    )

    task_ip = Task(
        id=uuid.uuid4(),
        project_id=proj.id,
        title="CAM Machining",
        task_code="TASK-001",
        status="IN_PROGRESS",
        planned_start_date=date(2026, 6, 25),
        planned_end_date=date(2026, 7, 2),
        is_active=True
    )

    task_fut = Task(
        id=uuid.uuid4(),
        project_id=proj.id,
        title="Inspection",
        task_code="TASK-002",
        status="NOT_STARTED",
        planned_start_date=date(2026, 7, 1),
        planned_end_date=date(2026, 7, 3),
        is_active=True
    )

    # 4 calls to db.scalars().all(): projects, tasks, dep 1, dep 2
    db.scalars.return_value.all.side_effect = [
        [proj],
        [task_ip, task_fut],
        [],
        []
    ]

    with patch("app.services.working_day_engine.WorkingDayEngine.is_weekend", return_value=False), \
         patch("app.services.working_day_engine.WorkingDayEngine.is_holiday", return_value=False), \
         patch("app.services.working_day_engine.WorkingDayEngine.next_working_day", side_effect=lambda d, db: d):
        
        impact = service.get_impact_analysis(holiday_id)
        
        assert impact["holiday_id"] == holiday_id
        assert len(impact["affected_projects"]) == 1
        assert len(impact["affected_tasks"]) == 2
        
        t_ip_impact = next(t for t in impact["affected_tasks"] if t["task_id"] == task_ip.id)
        assert t_ip_impact["proposed_start_date"] == date(2026, 6, 25)
        assert t_ip_impact["proposed_end_date"] == date(2026, 7, 3)
        
        t_fut_impact = next(t for t in impact["affected_tasks"] if t["task_id"] == task_fut.id)
        assert t_fut_impact["proposed_start_date"] == date(2026, 7, 2)
        assert t_fut_impact["proposed_end_date"] == date(2026, 7, 4)


def test_reject_emergency_holiday(db, service):
    holiday_id = uuid.uuid4()
    holiday = Holiday(
        id=holiday_id,
        name="Emergency Storm",
        date=date(2026, 7, 1),
        holiday_type="EMERGENCY",
        is_active=True
    )
    db.get.return_value = holiday

    res = service.reject_emergency_holiday(holiday_id)
    assert res["success"] is True
    assert "rejected" in res["message"].lower()
