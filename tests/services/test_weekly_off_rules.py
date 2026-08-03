import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from app.services.working_day_engine import WorkingDayEngine
from app.models.calendar_settings import CalendarSettings
from app.models.holiday import Holiday


@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


def test_get_day_ordinal():
    # 1st week: 1-7
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 1)) == 1
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 7)) == 1
    # 2nd week: 8-14
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 8)) == 2
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 14)) == 2
    # 3rd week: 15-21
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 15)) == 3
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 21)) == 3
    # 4th week: 22-28
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 22)) == 4
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 28)) == 4
    # 5th week: 29-31
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 29)) == 5
    assert WorkingDayEngine._get_day_ordinal(date(2026, 7, 31)) == 5


def test_is_weekly_off_no_rules(mock_db):
    with patch.object(WorkingDayEngine, "_get_weekly_off_rules", return_value={}):
        # Saturday, July 11, 2026 (2nd Saturday)
        dt = date(2026, 7, 11)
        assert WorkingDayEngine.is_weekly_off(dt, mock_db) is False


def test_is_weekly_off_with_rules(mock_db):
    # 2nd and 4th Saturday off
    rules = {"SAT": [2, 4]}
    with patch.object(WorkingDayEngine, "_get_weekly_off_rules", return_value=rules):
        # 1st Saturday: July 4, 2026 -> False
        assert WorkingDayEngine.is_weekly_off(date(2026, 7, 4), mock_db) is False
        # 2nd Saturday: July 11, 2026 -> True
        assert WorkingDayEngine.is_weekly_off(date(2026, 7, 11), mock_db) is True
        # 3rd Saturday: July 18, 2026 -> False
        assert WorkingDayEngine.is_weekly_off(date(2026, 7, 18), mock_db) is False
        # 4th Saturday: July 25, 2026 -> True
        assert WorkingDayEngine.is_weekly_off(date(2026, 7, 25), mock_db) is True
        # 5th Saturday: August 29, 2026 -> False
        assert WorkingDayEngine.is_weekly_off(date(2026, 8, 29), mock_db) is False


def test_is_off_day_precedence_no_double_counting(mock_db):
    # Setup rules: 2nd Saturday off
    rules = {"SAT": [2]}
    # Setup holidays: July 11, 2026 (which is 2nd Saturday)
    with patch.object(WorkingDayEngine, "_get_weekly_off_rules", return_value=rules), \
         patch.object(WorkingDayEngine, "_get_weekend_days", return_value={"SUN"}), \
         patch.object(WorkingDayEngine, "is_holiday", return_value=True):
        
        dt = date(2026, 7, 11)  # 2nd Saturday
        # It's a weekend (False, Sunday is weekend), weekly off (True), holiday (True)
        # Should be off day
        assert WorkingDayEngine.is_off_day(dt, mock_db) is True


def test_count_working_days_with_rules(mock_db):
    # Monday July 6, 2026 to Sunday July 12, 2026
    # Days: Mon 6, Tue 7, Wed 8, Thu 9, Fri 10, Sat 11 (2nd Sat), Sun 12 (Weekend)
    # If SAT [2] is weekly off, working days should be 5 (Mon-Fri)
    rules = {"SAT": [2]}
    with patch.object(WorkingDayEngine, "_get_weekly_off_rules", return_value=rules), \
         patch.object(WorkingDayEngine, "_get_weekend_days", return_value={"SUN"}), \
         patch.object(WorkingDayEngine, "get_holidays_in_range", return_value=set()):
        
        start = date(2026, 7, 6)
        end = date(2026, 7, 12)
        count = WorkingDayEngine.count_working_days(start, end, mock_db)
        assert count == 5  # Mon, Tue, Wed, Thu, Fri are working. Sat is weekly off. Sun is weekend.


def test_calculate_end_date_with_rules(mock_db):
    # Start: Friday July 10, 2026. Needs 16 hours (2 days of 8 hours).
    # Fri 10 (8 hrs spent -> remaining 8)
    # Sat 11 (2nd Sat, weekly off -> skipped)
    # Sun 12 (weekend -> skipped)
    # Mon 13 (8 hrs spent -> remaining 0)
    # End date should be Mon July 13.
    rules = {"SAT": [2]}
    with patch.object(WorkingDayEngine, "_get_weekly_off_rules", return_value=rules), \
         patch.object(WorkingDayEngine, "_get_weekend_days", return_value={"SUN"}), \
         patch.object(WorkingDayEngine, "_get_daily_hours", return_value=8.0), \
         patch.object(WorkingDayEngine, "get_holidays_in_range", return_value=set()):
        
        start = date(2026, 7, 10)
        end_dt = WorkingDayEngine.calculate_end_date(start, 16.0, mock_db)
        assert end_dt == date(2026, 7, 13)
