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
    Numeric,
    String,
    Text,
    func,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TaskRisk(Base):
    __tablename__ = "task_risks"

    __table_args__ = (
        Index("ix_task_risks_task_id", "task_id"),
        Index("ix_task_risks_employee_id", "employee_id"),
        Index("ix_task_risks_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    leave_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leave_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    leave_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    leave_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    remaining_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    days_impacted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    project_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING_MANAGER_ACTION", nullable=False
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

    task = relationship("Task", foreign_keys=[task_id])
    project = relationship("Project", foreign_keys=[project_id])
    assignment = relationship("TaskAssignment", foreign_keys=[assignment_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    leave_request = relationship("LeaveRequest", foreign_keys=[leave_request_id])


class TaskPauseHistory(Base):
    __tablename__ = "task_pause_history"

    __table_args__ = (
        Index("ix_task_pause_history_task_id", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    paused_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paused_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    resumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resumed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    task = relationship("Task", foreign_keys=[task_id])
    pauser = relationship("Employee", foreign_keys=[paused_by])
    resumer = relationship("Employee", foreign_keys=[resumed_by])


class TaskTransferHistory(Base):
    __tablename__ = "task_transfer_history"

    __table_args__ = (
        Index("ix_task_transfer_history_task_id", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=True,
    )
    to_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=True,
    )
    transfer_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    remaining_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    transfer_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "REASSIGN", "SPLIT"

    task = relationship("Task", foreign_keys=[task_id])
    from_employee = relationship("Employee", foreign_keys=[from_employee_id])
    to_employee = relationship("Employee", foreign_keys=[to_employee_id])
    manager = relationship("Employee", foreign_keys=[manager_id])


class TaskDelegation(Base):
    __tablename__ = "task_delegations"

    __table_args__ = (
        Index("ix_task_delegations_task_id", "task_id"),
        Index("ix_task_delegations_owner_id", "owner_id"),
        Index("ix_task_delegations_delegate_id", "delegate_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    delegate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delegated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", nullable=False
    )  # "ACTIVE", "COMPLETED"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    task = relationship("Task", foreign_keys=[task_id])
    owner = relationship("Employee", foreign_keys=[owner_id])
    delegate = relationship("Employee", foreign_keys=[delegate_id])
    delegator = relationship("Employee", foreign_keys=[delegated_by])


class ManagerDecision(Base):
    __tablename__ = "manager_decisions"

    __table_args__ = (
        Index("ix_manager_decisions_task_risk_id", "task_risk_id"),
        Index("ix_manager_decisions_task_id", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_risk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_risks.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "CONTINUE", "PAUSE", "REASSIGN", "SPLIT", "DELEGATE"
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task_risk = relationship("TaskRisk", foreign_keys=[task_risk_id])
    task = relationship("Task", foreign_keys=[task_id])
    manager = relationship("Employee", foreign_keys=[manager_id])
