from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TaskWorkSession(Base):
    __tablename__ = "task_work_sessions"

    __table_args__ = (
        Index("ix_tws_employee_id", "employee_id"),
        Index("ix_tws_task_id", "task_id"),
        Index("ix_tws_project_id", "project_id"),
        Index("ix_tws_status", "status"),
        Index("ix_tws_employee_status", "employee_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_type: Mapped[str] = mapped_column(
        String(20), default="REGULAR", nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="RUNNING", nullable=False
    )
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    ended_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    pause_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        "Employee",
        foreign_keys=[employee_id],
        back_populates="work_sessions",
    )
    task: Mapped["Task"] = relationship(
        "Task",
        foreign_keys=[task_id],
        back_populates="task_work_sessions",
    )
    project: Mapped["Project"] = relationship(
        "Project",
        foreign_keys=[project_id],
        back_populates="project_work_sessions",
    )
    starter: Mapped["Employee | None"] = relationship(
        "Employee",
        foreign_keys=[started_by],
    )
    ender: Mapped["Employee | None"] = relationship(
        "Employee",
        foreign_keys=[ended_by],
    )

    def __repr__(self) -> str:
        return (
            f"<TaskWorkSession {self.id}: employee={self.employee_id} "
            f"task={self.task_id} status={self.status} [{self.session_type}]>"
        )
