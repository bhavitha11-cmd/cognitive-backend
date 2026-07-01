from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Task(Base):
    __tablename__ = "tasks"

    __table_args__ = (
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_scope_of_work_id", "scope_of_work_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_department_category", "department_category"),
        Index("ix_tasks_parent_task_id", "parent_task_id"),
        Index("ix_tasks_is_active", "is_active"),
        Index("ix_tasks_team_id", "team_id"),
        UniqueConstraint("project_id", "task_code", name="uq_task_code_per_project"),
        CheckConstraint("parent_task_id != id", name="ck_task_no_self_parent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_code: Mapped[str] = mapped_column(String(100), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_of_work_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scope_of_work.id", ondelete="SET NULL"),
        nullable=True,
    )
    department_category: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="NOT_STARTED", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    estimated_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0, server_default="0", nullable=False)
    actual_hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0, server_default="0", nullable=False)
    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scheduled_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scheduled_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress: Mapped[float] = mapped_column(Numeric(5, 4), default=0, server_default="0", nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Rework tracking
    rework_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_rework_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, server_default="0", nullable=False
    )
    original_estimated_hours: Mapped[float | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )

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

    project: Mapped["Project"] = relationship("Project", back_populates="tasks")
    team: Mapped["Team"] = relationship("Team", foreign_keys=[team_id])
    scope: Mapped["ScopeOfWork | None"] = relationship("ScopeOfWork", back_populates="tasks")
    parent_task: Mapped["Task | None"] = relationship(
        "Task",
        remote_side="Task.id",
        back_populates="sub_tasks",
        foreign_keys=[parent_task_id],
    )
    sub_tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="parent_task",
        foreign_keys=[parent_task_id],
    )
    assignments: Mapped[list["TaskAssignment"]] = relationship(
        "TaskAssignment", back_populates="task", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list["TaskDependency"]] = relationship(
        "TaskDependency",
        foreign_keys="[TaskDependency.task_id]",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    task_time_entries: Mapped[list["TimeEntry"]] = relationship(
        "TimeEntry", foreign_keys="[TimeEntry.task_id]", back_populates="task"
    )
    task_work_sessions: Mapped[list["TaskWorkSession"]] = relationship(
        "TaskWorkSession", foreign_keys="[TaskWorkSession.task_id]", back_populates="task"
    )
    rework_history: Mapped[list["TaskReworkHistory"]] = relationship(
        "TaskReworkHistory", foreign_keys="[TaskReworkHistory.task_id]", back_populates="task"
    )

    def __repr__(self) -> str:
        return f"<Task {self.task_code}: {self.title} [{self.status}]>"
