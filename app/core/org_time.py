from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from app.core.config import settings

ORG_TZ = ZoneInfo(settings.ORG_TIMEZONE)


def org_now() -> datetime:
    return datetime.now(ORG_TZ)


def to_org(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ORG_TZ)


def business_date(dt: datetime | None = None) -> date:
    return (org_now() if dt is None else to_org(dt)).date()


def get_org_today_range(target_date: date | None = None) -> tuple[datetime, datetime]:
    if target_date is None:
        now = org_now()
        year, month, day = now.year, now.month, now.day
    else:
        year, month, day = target_date.year, target_date.month, target_date.day
    start_local = datetime(year, month, day, 0, 0, 0, tzinfo=ORG_TZ)
    end_local = datetime(year, month, day, 23, 59, 59, 999999, tzinfo=ORG_TZ)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
