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
