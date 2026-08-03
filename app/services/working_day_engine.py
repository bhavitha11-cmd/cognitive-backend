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
    def _get_weekly_off_rules(db: Session) -> dict[str, list[int]]:
        """Return the weekly off rules dict, e.g. {"SAT": [2, 4]}."""
        from app.models.calendar_settings import CalendarSettings
        settings = db.scalar(select(CalendarSettings))
        if settings and settings.weekly_off_rules:
            return settings.weekly_off_rules
        return {}

    @staticmethod
    def _get_daily_hours(db: Session) -> float:
        from app.models.calendar_settings import CalendarSettings
        settings = db.scalar(select(CalendarSettings))
        if settings:
            return float(settings.working_hours_per_day)
        return 8.0

    @staticmethod
    def _get_day_ordinal(dt: date) -> int:
        """Return which occurrence of this weekday in the month (1-5).

        1st occurrence = days 1-7, 2nd = 8-14, 3rd = 15-21,
        4th = 22-28, 5th = 29-31.
        """
        return (dt.day - 1) // 7 + 1

    # ── Individual off-day checks ────────────────────────────────────────────

    @classmethod
    def is_weekend(cls, dt: date, db: Session) -> bool:
        """Check if the date falls on a full-week weekend day."""
        weekend_days = cls._get_weekend_days(db)
        return _WEEKEND_DAY_NAMES[dt.weekday()] in weekend_days

    @classmethod
    def is_holiday(cls, dt: date, db: Session) -> bool:
        """Check if the date is an active company holiday."""
        result = db.scalar(
            select(Holiday.id).where(
                Holiday.date == dt,
                Holiday.is_active == True,
            )
        )
        return result is not None

    @classmethod
    def is_weekly_off(cls, dt: date, db: Session) -> bool:
        """Check if the date matches a weekly off rule (e.g. 2nd & 4th Saturday)."""
        day_name = _WEEKEND_DAY_NAMES[dt.weekday()]
        off_rules = cls._get_weekly_off_rules(db)
        if day_name in off_rules:
            ordinal = cls._get_day_ordinal(dt)
            return ordinal in off_rules[day_name]
        return False

    # ── Unified off-day check (single source of truth) ───────────────────────

    @classmethod
    def is_off_day(cls, dt: date, db: Session) -> bool:
        """Unified check: a day is off if it is a weekend OR holiday OR weekly-off-rule.

        No double-counting — one day is one off day regardless of how many
        rules match it.
        """
        if cls.is_weekend(dt, db):
            return True
        if cls.is_weekly_off(dt, db):
            return True
        if cls.is_holiday(dt, db):
            return True
        return False

    @classmethod
    def is_working_day(cls, dt: date, db: Session) -> bool:
        return not cls.is_off_day(dt, db)

    # ── Bulk calculations ────────────────────────────────────────────────────

    @classmethod
    def count_working_days(cls, start: date, end: date, db: Session) -> int:
        if start > end:
            return 0
        # Pre-fetch all data to avoid repeated DB calls in the loop
        weekend_days = cls._get_weekend_days(db)
        off_rules = cls._get_weekly_off_rules(db)
        holidays = cls.get_holidays_in_range(start, end, db)
        count = 0
        current = start
        while current <= end:
            day_name = _WEEKEND_DAY_NAMES[current.weekday()]
            # Weekend check
            if day_name in weekend_days:
                current += timedelta(days=1)
                continue
            # Weekly off rule check
            if day_name in off_rules:
                ordinal = (current.day - 1) // 7 + 1
                if ordinal in off_rules[day_name]:
                    current += timedelta(days=1)
                    continue
            # Holiday check
            if current in holidays:
                current += timedelta(days=1)
                continue
            count += 1
            current += timedelta(days=1)
        return count

    @classmethod
    def calculate_end_date(cls, start: date, hours: float, db: Session) -> date:
        if hours <= 0:
            return start
        daily_hours = cls._get_daily_hours(db)
        # Pre-fetch settings
        weekend_days = cls._get_weekend_days(db)
        off_rules = cls._get_weekly_off_rules(db)
        holidays = cls.get_holidays_in_range(start, start + timedelta(days=int(hours / daily_hours) * 2 + 30), db)
        remaining = hours
        current = start
        last_working = start
        while remaining > 0:
            day_name = _WEEKEND_DAY_NAMES[current.weekday()]
            # Check if this day is off (weekend, weekly rule, or holiday)
            is_off = False
            if day_name in weekend_days:
                is_off = True
            elif day_name in off_rules:
                ordinal = (current.day - 1) // 7 + 1
                if ordinal in off_rules[day_name]:
                    is_off = True
            if not is_off and current in holidays:
                is_off = True

            if is_off:
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
