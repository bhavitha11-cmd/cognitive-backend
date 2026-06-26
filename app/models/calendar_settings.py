from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CalendarSettings(Base):
    __tablename__ = "calendar_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    working_days: Mapped[str] = mapped_column(
        String(100), default="MON,TUE,WED,THU,FRI,SAT", nullable=False
    )
    weekend_days: Mapped[str] = mapped_column(
        String(100), default="SUN", nullable=False
    )
    office_start_time: Mapped[str] = mapped_column(
        String(5), default="09:00", nullable=False
    )
    office_end_time: Mapped[str] = mapped_column(
        String(5), default="18:00", nullable=False
    )
    default_daily_hours: Mapped[float] = mapped_column(
        Float, default=8.0, nullable=False
    )
    working_hours_per_day: Mapped[float] = mapped_column(
        Float, default=8.0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CalendarSettings working_days={self.working_days}>"
