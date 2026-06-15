from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AttendanceRule(Base):
    __tablename__ = "attendance_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    office_start_time: Mapped[str] = mapped_column(
        String(5), default="09:00", nullable=False
    )
    office_end_time: Mapped[str] = mapped_column(
        String(5), default="18:00", nullable=False
    )
    half_day_hours: Mapped[float] = mapped_column(
        Numeric(4, 2), default=4.0, nullable=False
    )
    late_mark_after_minutes: Mapped[int] = mapped_column(
        Integer, default=15, nullable=False
    )
    work_days: Mapped[str] = mapped_column(
        String(50), default="MON,TUE,WED,THU,FRI", nullable=False
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
        return f"<AttendanceRule start={self.office_start_time} end={self.office_end_time}>"
