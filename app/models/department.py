from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    department_head_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
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

    department_head: Mapped["Employee | None"] = relationship(
        "Employee",
        foreign_keys=[department_head_id],
        post_update=True,
    )

    employees: Mapped[list["Employee"]] = relationship(
        "Employee",
        back_populates="department",
        foreign_keys="Employee.department_id",
    )

    designations: Mapped[list["Designation"]] = relationship(
        "Designation",
        back_populates="department",
        cascade="all, delete-orphan",
    )

    @property
    def employee_count(self) -> int:
        return len(self.employees)

    @property
    def department_head_name(self) -> str | None:
        if self.department_head:
            return f"{self.department_head.first_name} {self.department_head.last_name}"
        return None

    def __repr__(self) -> str:
        return f"<Department {self.name}>"

