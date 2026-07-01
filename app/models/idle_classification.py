from __future__ import annotations

import uuid
from datetime import date as date_type, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class IdleClassification(Base):
    __tablename__ = "idle_classifications"

    __table_args__ = (
        UniqueConstraint(
            "employee_id", "date", "idle_segment_identifier", name="uq_idle_classifications"
        ),
        Index("ix_idle_class_emp_date", "employee_id", "date"),
        Index("ix_idle_classifications_reason_id", "reason_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date_type] = mapped_column(
        Date, nullable=False, index=True
    )
    idle_segment_identifier: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    reason_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idle_reason_master.id", ondelete="CASCADE"),
        nullable=False,
    )
    remarks: Mapped[str | None] = mapped_column(
        Text, nullable=True
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

    employee: Mapped["Employee"] = relationship(
        "Employee", foreign_keys=[employee_id]
    )
    reason: Mapped["IdleReasonMaster"] = relationship(
        "IdleReasonMaster", foreign_keys=[reason_id]
    )

    def __repr__(self) -> str:
        return (
            f"<IdleClassification {self.id}: employee={self.employee_id} "
            f"date={self.date} segment={self.idle_segment_identifier} reason={self.reason_id}>"
        )
