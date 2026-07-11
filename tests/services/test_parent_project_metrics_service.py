from datetime import date
from unittest.mock import MagicMock, patch
from uuid import UUID
import pytest

from app.services.parent_project_metrics_service import ParentProjectMetricsService

def make_part(
    status: str = "Yet To Start",
    estimated_hours: float = 10.0,
    actual_hours: float = 0.0,
    progress: float = 0.0,
    planned_start_date: date | None = None,
    planned_end_date: date | None = None,
    actual_start_date: date | None = None,
    actual_end_date: date | None = None,
) -> MagicMock:
    p = MagicMock()
    p.status = status
    p.estimated_hours = estimated_hours
    p.actual_hours = actual_hours
    p.progress = progress
    p.planned_start_date = planned_start_date
    p.planned_end_date = planned_end_date
    p.actual_start_date = actual_start_date
    p.actual_end_date = actual_end_date
    p.is_active = True
    return p

class TestParentProjectRecalculate:
    def test_no_parts_resets_metrics(self):
        db = MagicMock()
        parent = MagicMock()
        parent.id = UUID("11111111-1111-1111-1111-111111111111")
        parent.is_active = True
        db.get.return_value = parent
        
        # Mock the db query to return no parts
        db.scalars.return_value.all.return_value = []

        with patch("app.services.parent_project_metrics_service.AuditService"):
            result = ParentProjectMetricsService.recalculate(db, parent.id)

        assert result["new"]["estimated_hours"] == 0.0
        assert result["new"]["actual_hours"] == 0.0
        assert result["new"]["progress"] == 0.0
        assert result["new"]["status"] == "Yet To Start"
        assert result["new"]["planned_start_date"] is None
        assert result["new"]["planned_end_date"] is None

    def test_computes_rolled_up_metrics(self):
        db = MagicMock()
        parent = MagicMock()
        parent.id = UUID("11111111-1111-1111-1111-111111111111")
        parent.is_active = True
        db.get.return_value = parent

        p1 = make_part(
            status="In Progress",
            estimated_hours=40.0,
            actual_hours=10.0,
            progress=25.0,
            planned_start_date=date(2026, 1, 5),
            planned_end_date=date(2026, 1, 20),
        )
        p2 = make_part(
            status="Completed",
            estimated_hours=60.0,
            actual_hours=60.0,
            progress=100.0,
            planned_start_date=date(2026, 1, 2),
            planned_end_date=date(2026, 1, 15),
        )
        
        # Mock the db query to return our mocked parts
        db.scalars.return_value.all.return_value = [p1, p2]

        with patch("app.services.parent_project_metrics_service.AuditService"):
            result = ParentProjectMetricsService.recalculate(db, parent.id)

        # Totals
        assert result["new"]["estimated_hours"] == 100.0
        assert result["new"]["actual_hours"] == 70.0
        
        # Weighted Progress: (25% * 40h + 100% * 60h) / 100h = 70.0%
        assert result["new"]["progress"] == 70.0
        
        # Status derivation: mix of In Progress and Completed -> In Progress
        assert result["new"]["status"] == "In Progress"
        
        # Date boundaries
        assert result["new"]["planned_start_date"] == str(date(2026, 1, 2))
        assert result["new"]["planned_end_date"] == str(date(2026, 1, 20))
