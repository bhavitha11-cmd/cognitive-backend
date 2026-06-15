from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class EmployeeSchedule(Base):
    __tablename__ = "employee_schedules"

    __table_args__ = (
        UniqueConstraint("employee_id", "week_start_date", name="uq_employee_week"),
        Index("ix_employee_schedules_employee_id", "employee_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    available_hours: Mapped[float] = mapped_column(
        Numeric(5, 2), default=40.0, nullable=False
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

    employee: Mapped["Employee"] = relationship("Employee", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<EmployeeSchedule {self.employee_id} week={self.week_start_date}>"
        )
