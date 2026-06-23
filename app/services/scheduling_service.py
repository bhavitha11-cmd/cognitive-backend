from datetime import date, datetime, timedelta, time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.holiday import Holiday
from app.models.attendance_rule import AttendanceRule

class SchedulingService:
    @staticmethod
    def is_weekend(dt: date) -> bool:
        # Saturday = 5, Sunday = 6
        return dt.weekday() in (5, 6)

    @staticmethod
    def get_holidays_in_range(start_date: date, end_date: date, db: Session) -> set[date]:
        stmt = select(Holiday.date).where(Holiday.date.between(start_date, end_date))
        results = db.scalars(stmt).all()
        return set(results)

    @staticmethod
    def get_all_holidays(db: Session) -> set[date]:
        stmt = select(Holiday.date)
        results = db.scalars(stmt).all()
        return set(results)

    @staticmethod
    def get_remaining_hours_today(office_end_hour: float = 18.0) -> float:
        now = datetime.now()
        # Cap working capacity to 8 hours max, and 0 min
        current_time_float = now.hour + now.minute / 60.0
        remaining = office_end_hour - current_time_float
        return min(8.0, max(0.0, remaining))

    @classmethod
    def calculate_working_hours(cls, start_date: date, end_date: date, db: Session) -> float:
        if start_date > end_date:
            return 0.0

        holidays = cls.get_holidays_in_range(start_date, end_date, db)
        total_hours = 0.0
        current = start_date
        today = date.today()

        # Get office end hour from attendance rules if available, default to 18.0 (6:00 PM)
        office_end_hour = 18.0
        rule = db.scalars(select(AttendanceRule)).first()
        if rule and rule.office_end_time:
            try:
                parts = rule.office_end_time.split(":")
                office_end_hour = float(parts[0]) + float(parts[1]) / 60.0
            except Exception:
                pass

        while current <= end_date:
            if cls.is_weekend(current) or current in holidays:
                current += timedelta(days=1)
                continue

            if current == today:
                total_hours += cls.get_remaining_hours_today(office_end_hour)
            else:
                total_hours += 8.0

            current += timedelta(days=1)

        return total_hours

    @classmethod
    def calculate_end_date(cls, start_date: date, estimated_hours: float, db: Session) -> date:
        if estimated_hours <= 0:
            return start_date

        # Estimate a safe maximum end date to fetch holidays in range
        # 8 hours/day, so days = estimated_hours / 8. With weekends/holidays, let's pull a generous window.
        estimated_days = int(estimated_hours / 8.0) + 1
        safe_window_days = estimated_days * 3 + 30
        end_estimate = start_date + timedelta(days=safe_window_days)
        holidays = cls.get_holidays_in_range(start_date, end_estimate, db)

        # Get office end hour
        office_end_hour = 18.0
        rule = db.scalars(select(AttendanceRule)).first()
        if rule and rule.office_end_time:
            try:
                parts = rule.office_end_time.split(":")
                office_end_hour = float(parts[0]) + float(parts[1]) / 60.0
            except Exception:
                pass

        remaining_hours = estimated_hours
        current = start_date
        today = date.today()
        last_working_day = start_date

        while remaining_hours > 0:
            # If current day is weekend or holiday, skip it
            if cls.is_weekend(current) or current in holidays:
                current += timedelta(days=1)
                continue

            last_working_day = current
            # Calculate capacity for this day
            if current == today:
                capacity = cls.get_remaining_hours_today(office_end_hour)
            else:
                capacity = 8.0

            # If capacity is 0, we can't make progress on this day. Skip it to prevent infinite loop.
            if capacity <= 0:
                current += timedelta(days=1)
                continue

            if remaining_hours <= capacity:
                remaining_hours = 0
            else:
                remaining_hours -= capacity
                current += timedelta(days=1)

        return last_working_day
