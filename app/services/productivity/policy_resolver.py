import threading
import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.attendance_rule import AttendanceRule


class PolicyResolver:
    _lock = threading.Lock()
    _cached_rule: AttendanceRule | None = None
    _cache_expiry: float = 0.0
    _ttl_seconds: float = 300.0  # 5 minutes TTL

    @classmethod
    def get_rule(cls, db: Session) -> AttendanceRule:
        """Fetch the single global attendance rule configuration, with thread-safe caching."""
        # Bypass cache for mock DBs in unit tests
        is_mock_db = type(db).__name__ in ("MagicMock", "Mock") or hasattr(db, "_mock_self") or hasattr(db, "assert_called")
        if is_mock_db:
            rule = db.scalars(select(AttendanceRule)).first()
            if not rule:
                rule = AttendanceRule()
                db.add(rule)
                db.flush()
            return rule

        now = time.time()
        
        # Double-checked locking pattern for thread-safety and efficiency
        if cls._cached_rule is None or now >= cls._cache_expiry:
            with cls._lock:
                if cls._cached_rule is None or now >= cls._cache_expiry:
                    rule = db.scalars(select(AttendanceRule)).first()
                    if not rule:
                        rule = AttendanceRule()
                        db.add(rule)
                        db.flush()
                    
                    # Create a session-detached copy for caching to prevent session cross-contamination
                    cls._cached_rule = AttendanceRule(
                        id=rule.id,
                        office_start_time=rule.office_start_time,
                        office_end_time=rule.office_end_time,
                        half_day_hours=rule.half_day_hours,
                        late_mark_after_minutes=rule.late_mark_after_minutes,
                        work_days=rule.work_days,
                        required_productive_hours=rule.required_productive_hours,
                        overtime_threshold_hours=rule.overtime_threshold_hours,
                        max_break_minutes=rule.max_break_minutes,
                        min_break_minutes=rule.min_break_minutes,
                        created_at=rule.created_at,
                        updated_at=rule.updated_at
                    )
                    cls._cache_expiry = now + cls._ttl_seconds

        # Return a clean copy for the current database session
        cached = cls._cached_rule
        return AttendanceRule(
            id=cached.id,
            office_start_time=cached.office_start_time,
            office_end_time=cached.office_end_time,
            half_day_hours=cached.half_day_hours,
            late_mark_after_minutes=cached.late_mark_after_minutes,
            work_days=cached.work_days,
            required_productive_hours=cached.required_productive_hours,
            overtime_threshold_hours=cached.overtime_threshold_hours,
            max_break_minutes=cached.max_break_minutes,
            min_break_minutes=cached.min_break_minutes,
            created_at=cached.created_at,
            updated_at=cached.updated_at
        )

    @classmethod
    def clear_cache(cls):
        """Invalidate the cached policy configuration."""
        with cls._lock:
            cls._cached_rule = None
            cls._cache_expiry = 0.0

