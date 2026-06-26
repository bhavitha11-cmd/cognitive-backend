from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    __table_args__ = (
        Index("ix_calendar_events_dates", "start_date", "end_date"),
        Index("ix_calendar_events_type_active", "event_type", "is_active"),
        Index("ix_calendar_events_reference", "reference_type", "reference_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="COMPANY_EVENT"
    )
    event_subtype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    text_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
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

    creator: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[created_by]
    )

    def __repr__(self) -> str:
        return f"<CalendarEvent {self.title} on {self.start_date}>"
