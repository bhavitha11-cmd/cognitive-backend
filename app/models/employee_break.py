from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class EmployeeBreak(Base):
    __tablename__ = "employee_breaks"

    __table_args__ = (
        Index("ix_emp_breaks_employee_id", "employee_id"),
        Index("ix_emp_breaks_date", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    break_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    break_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(
        "Employee",
        foreign_keys=[employee_id],
        backref="breaks",
    )

    def __repr__(self) -> str:
        return (
            f"<EmployeeBreak {self.id}: employee={self.employee_id} "
            f"date={self.date} start={self.break_start}>"
        )
