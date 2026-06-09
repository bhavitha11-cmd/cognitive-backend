from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class EmployeeRoleHistory(Base):
    __tablename__ = "employee_role_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(
        Date, nullable=False
    )
    effective_to: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    reason: Mapped[str] = mapped_column(
        String(100), nullable=False
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
    old_role: Mapped["Role | None"] = relationship(
        "Role", foreign_keys=[old_role_id]
    )
    new_role: Mapped["Role"] = relationship(
        "Role", foreign_keys=[new_role_id]
    )
    changer: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[changed_by]
    )

    def __repr__(self) -> str:
        return f"<EmployeeRoleHistory emp={self.employee_id} new_role={self.new_role_id}>"
