from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
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


class Employee(Base):
    __tablename__ = "employees"

    __table_args__ = (
        Index("ix_employees_department_id", "department_id"),
        Index("ix_employees_designation_id", "designation_id"),
        Index("ix_employees_reporting_manager_id", "reporting_manager_id"),
        Index("ix_employees_account_status", "account_status"),
        Index("ix_employees_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    official_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    personal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mobile_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    designation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("designations.id", ondelete="SET NULL"),
        nullable=True,
    )
    reporting_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", nullable=False
    )
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Offboarding fields
    resignation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_working_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offboard_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    offboard_initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    successor_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    department: Mapped["Department | None"] = relationship(
        "Department", back_populates="employees", foreign_keys=[department_id]
    )
    designation: Mapped["Designation | None"] = relationship(
        "Designation", foreign_keys=[designation_id], back_populates="employees"
    )
    reporting_manager: Mapped["Employee | None"] = relationship(
        "Employee",
        remote_side="Employee.id",
        back_populates="direct_reports",
        foreign_keys=[reporting_manager_id],
    )
    direct_reports: Mapped[list["Employee"]] = relationship(
        "Employee",
        back_populates="reporting_manager",
        foreign_keys=[reporting_manager_id],
    )
    employee_roles: Mapped[list["EmployeeRole"]] = relationship(
        "EmployeeRole", back_populates="employee", cascade="all, delete-orphan"
    )
    team_assignments: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="employee", cascade="all, delete-orphan"
    )
    time_entries: Mapped[list["TimeEntry"]] = relationship(
        "TimeEntry", foreign_keys="[TimeEntry.employee_id]", back_populates="employee"
    )
    work_sessions: Mapped[list["TaskWorkSession"]] = relationship(
        "TaskWorkSession", foreign_keys="[TaskWorkSession.employee_id]", back_populates="employee"
    )
    breaks: Mapped[list["EmployeeBreak"]] = relationship(
        "EmployeeBreak", foreign_keys="[EmployeeBreak.employee_id]", back_populates="employee"
    )

    def __repr__(self) -> str:
        return f"<Employee {self.employee_code}: {self.first_name} {self.last_name}>"
