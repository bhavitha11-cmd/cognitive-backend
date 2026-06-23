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


class TaskReworkHistory(Base):
    __tablename__ = "task_rework_history"

    __table_args__ = (
        Index("ix_trh_task_id", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    rework_number: Mapped[int] = mapped_column(Integer, nullable=False)
    opened_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hours_spent: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped["Task"] = relationship(
        "Task",
        foreign_keys=[task_id],
        backref="rework_history",
    )
    opener: Mapped["Employee | None"] = relationship(
        "Employee",
        foreign_keys=[opened_by],
    )

    def __repr__(self) -> str:
        return (
            f"<TaskReworkHistory {self.id}: task={self.task_id} "
            f"rework={self.rework_number}>"
        )
