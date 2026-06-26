from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holiday import Holiday


_WEEKEND_DAY_NAMES: dict[int, str] = {
    0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI", 5: "SAT", 6: "SUN",
}


class WorkingDayEngine:
    """Stateless utility — all @classmethod or @staticmethod. Never instantiated."""

    @staticmethod
    def _get_weekend_days(db: Session) -> set[str]:
        from app.models.calendar_settings import CalendarSettings
        settings = db.scalar(select(CalendarSettings))
        if settings and settings.weekend_days:
            return {d.strip().upper() for d in settings.weekend_days.split(",")}
        return {"SUN"}

    @staticmethod
    def _get_daily_hours(db: Session) -> float:
        from app.models.calendar_settings import CalendarSettings
        settings = db.scalar(select(CalendarSettings))
        if settings:
            return float(settings.working_hours_per_day)
        return 8.0

    @classmethod
    def is_weekend(cls, dt: date, db: Session) -> bool:
        weekend_days = cls._get_weekend_days(db)
        return _WEEKEND_DAY_NAMES[dt.weekday()] in weekend_days

    @classmethod
    def is_holiday(cls, dt: date, db: Session) -> bool:
        result = db.scalar(
            select(Holiday.id).where(
                Holiday.date == dt,
                Holiday.is_active == True,
            )
        )
        return result is not None

    @classmethod
    def is_working_day(cls, dt: date, db: Session) -> bool:
        return not cls.is_weekend(dt, db) and not cls.is_holiday(dt, db)

    @classmethod
    def count_working_days(cls, start: date, end: date, db: Session) -> int:
        if start > end:
            return 0
        holidays = cls.get_holidays_in_range(start, end, db)
        weekend_days = cls._get_weekend_days(db)
        count = 0
        current = start
        while current <= end:
            if _WEEKEND_DAY_NAMES[current.weekday()] not in weekend_days and current not in holidays:
                count += 1
            current += timedelta(days=1)
        return count

    @classmethod
    def calculate_end_date(cls, start: date, hours: float, db: Session) -> date:
        if hours <= 0:
            return start
        daily_hours = cls._get_daily_hours(db)
        holidays = cls.get_holidays_in_range(start, start + timedelta(days=int(hours / daily_hours) * 2 + 30), db)
        weekend_days = cls._get_weekend_days(db)
        remaining = hours
        current = start
        last_working = start
        while remaining > 0:
            if _WEEKEND_DAY_NAMES[current.weekday()] in weekend_days or current in holidays:
                current += timedelta(days=1)
                continue
            last_working = current
            if remaining <= daily_hours:
                remaining = 0
            else:
                remaining -= daily_hours
                current += timedelta(days=1)
        return last_working

    @classmethod
    def next_working_day(cls, dt: date, db: Session) -> date:
        current = dt
        while not cls.is_working_day(current, db):
            current += timedelta(days=1)
        return current

    @classmethod
    def previous_working_day(cls, dt: date, db: Session) -> date:
        current = dt
        while not cls.is_working_day(current, db):
            current -= timedelta(days=1)
        return current

    @classmethod
    def monthly_working_days(cls, year: int, month: int, db: Session) -> int:
        from calendar import monthrange
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        return cls.count_working_days(first, last, db)

    @classmethod
    def add_working_days(cls, start: date, days: int, db: Session) -> date:
        if days <= 0:
            return start
        daily_hours = cls._get_daily_hours(db)
        return cls.calculate_end_date(start, days * daily_hours, db)

    @classmethod
    def get_holidays_in_range(cls, start: date, end: date, db: Session) -> set[date]:
        rows = db.scalars(
            select(Holiday.date).where(
                Holiday.date.between(start, end),
                Holiday.is_active == True,
            )
        ).all()
        return set(rows)
