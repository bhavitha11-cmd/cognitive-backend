from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class EmployeeReportingHistory(Base):
    __tablename__ = "employee_reporting_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(
        "Employee", foreign_keys=[employee_id]
    )
    old_manager: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[old_manager_id]
    )
    new_manager: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[new_manager_id]
    )
    changer: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[changed_by]
    )

    def __repr__(self) -> str:
        return f"<EmployeeReportingHistory emp={self.employee_id}>"
