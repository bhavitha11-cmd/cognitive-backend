from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ParentProject(Base):
    __tablename__ = "parent_projects"

    __table_args__ = (
        Index("ix_parent_projects_client_id", "client_id"),
        Index("ix_parent_projects_project_manager_id", "project_manager_id"),
        Index("ix_parent_projects_department_id", "department_id"),
        Index("ix_parent_projects_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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

    # Rolled-up metrics (cached and recalculated from Parts)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Yet To Start")
    progress: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0, server_default="0"
    )
    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    actual_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )

    # Relationships
    client: Mapped["Client"] = relationship("Client", foreign_keys=[client_id])
    project_manager: Mapped["Employee | None"] = relationship("Employee", foreign_keys=[project_manager_id])
    department: Mapped["Department"] = relationship("Department", foreign_keys=[department_id])
    parts: Mapped[list["Project"]] = relationship("Project", back_populates="parent_project", lazy="select")
