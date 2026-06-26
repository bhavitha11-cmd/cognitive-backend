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


class Project(Base):
    __tablename__ = "projects"

    __table_args__ = (
        Index("ix_projects_client_id", "client_id"),
        Index("ix_projects_project_manager_id", "project_manager_id"),
        Index("ix_projects_status", "status"),
        Index("ix_projects_is_active", "is_active"),
        Index("ix_projects_created_by", "created_by"),
        Index("ix_projects_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    part_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
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
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Status / classification
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Yet To Start")
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Dates
    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Hours / billing
    estimated_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )
    # Auto-computed from tasks — do NOT set manually
    actual_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )
    # Hour-weighted progress 0.00–100.00 — auto-computed from tasks
    progress: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0
    )
    contract_hours: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Invoice / feedback
    invoice_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )
    tok_form: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feedback_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
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

    # Relationships
    client: Mapped["Client"] = relationship(
        "Client", foreign_keys=[client_id], back_populates="projects"
    )
    project_manager: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[project_manager_id]
    )
    department: Mapped["Department"] = relationship(
        "Department", foreign_keys=[department_id]
    )
    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="project", lazy="select"
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="project", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Project {self.project_code}: {self.name}>"
