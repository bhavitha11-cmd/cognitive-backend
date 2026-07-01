from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class PendingScheduleReview(Base):
    """One review entry per (holiday, project) pair.

    Lifecycle:
        PENDING  → created automatically when an Emergency Holiday is saved
        APPLIED  → project manager accepted and applied the proposed schedule
        REJECTED → project manager chose to keep the existing schedule

    The ``project_manager_id`` column mirrors the ``project_manager_id`` on
    the related Project record at the time the review was created.  It is
    stored here so that the dashboard query can filter by owner without
    joining back to the projects table.
    """

    __tablename__ = "pending_schedule_reviews"

    __table_args__ = (
        # Prevent duplicate reviews for the same (holiday, project) pair
        UniqueConstraint("holiday_id", "project_id", name="uq_psr_holiday_project"),
        # Primary read path: owner-scoped dashboard query
        Index("ix_psr_manager_status", "project_manager_id", "review_status"),
        # Used when deactivating a holiday to cancel its open reviews
        Index("ix_psr_holiday_id", "holiday_id"),
        # Domain constraint on review_status
        CheckConstraint(
            "review_status IN ('PENDING', 'APPLIED', 'REJECTED')",
            name="ck_psr_review_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    holiday_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("holidays.id", ondelete="CASCADE"),
        nullable=False,
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Denormalised from project.project_manager_id at review-creation time.
    # Nullable because a project may have no assigned manager.
    project_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )

    # Optional free-text note (e.g. rejection reason)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who actioned this review (applied or rejected it)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    # ── Relationships ─────────────────────────────────────────────────────────
    holiday: Mapped["Holiday"] = relationship(
        "Holiday", foreign_keys=[holiday_id], lazy="select"
    )
    project: Mapped["Project"] = relationship(
        "Project", foreign_keys=[project_id], lazy="select"
    )
    project_manager: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[project_manager_id], lazy="select"
    )
    reviewer: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[reviewed_by], lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<PendingScheduleReview {self.id} "
            f"project={self.project_id} status={self.review_status}>"
        )
