from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    days_per_year: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_carry_forward: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    max_carry_forward_days: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    requires_document: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    color: Mapped[str] = mapped_column(
        String(7), default="#3B82F6", nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        "LeaveRequest", back_populates="leave_type"
    )
    leave_balances: Mapped[list["LeaveBalance"]] = relationship(
        "LeaveBalance", back_populates="leave_type"
    )

    def __repr__(self) -> str:
        return f"<LeaveType {self.code}: {self.name}>"
