from datetime import date, datetime, timedelta, time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.holiday import Holiday
from app.models.attendance_rule import AttendanceRule
from app.services.working_day_engine import WorkingDayEngine


class SchedulingService:
    """Backward-compatible wrapper that delegates all date logic to WorkingDayEngine."""

    @staticmethod
    def is_weekend(dt: date) -> bool:
        return dt.weekday() in (5, 6)

    @staticmethod
    def get_holidays_in_range(start_date: date, end_date: date, db: Session) -> set[date]:
        return WorkingDayEngine.get_holidays_in_range(start_date, end_date, db)

    @staticmethod
    def get_all_holidays(db: Session) -> set[date]:
        results = db.scalars(select(Holiday.date)).all()
        return set(results)

    @staticmethod
    def get_remaining_hours_today(office_end_hour: float = 18.0) -> float:
        now = datetime.now()
        current_time_float = now.hour + now.minute / 60.0
        remaining = office_end_hour - current_time_float
        return min(8.0, max(0.0, remaining))

    @classmethod
    def calculate_working_hours(cls, start_date: date, end_date: date, db: Session) -> float:
        return float(WorkingDayEngine.count_working_days(start_date, end_date, db) * 8)

    @classmethod
    def calculate_end_date(cls, start_date: date, estimated_hours: float, db: Session) -> date:
        return WorkingDayEngine.calculate_end_date(start_date, estimated_hours, db)
