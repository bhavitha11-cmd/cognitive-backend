from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflows"

    __table_args__ = (
        Index("ix_approval_workflows_module_type", "module_type"),
        Index("ix_approval_workflows_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    module_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approval_strategy: Mapped[str] = mapped_column(
        String(50), default="ANY_ONE", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    steps: Mapped[list[ApprovalWorkflowStep]] = relationship(
        "ApprovalWorkflowStep",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="ApprovalWorkflowStep.level",
    )
    instances: Mapped[list[ApprovalInstance]] = relationship(
        "ApprovalInstance", back_populates="workflow", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ApprovalWorkflow {self.name} v{self.version} module={self.module_type}>"


class ApprovalWorkflowStep(Base):
    __tablename__ = "approval_workflow_steps"

    __table_args__ = (
        Index("ix_approval_workflow_steps_workflow_id", "workflow_id"),
        Index("ix_approval_workflow_steps_requester_role_id", "requester_role_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    resolution_scope: Mapped[str] = mapped_column(String(50), nullable=False)

    workflow: Mapped[ApprovalWorkflow] = relationship(
        "ApprovalWorkflow", back_populates="steps"
    )
    requester_role: Mapped["Role"] = relationship(
        "Role", foreign_keys=[requester_role_id]
    )
    approver_role: Mapped["Role"] = relationship(
        "Role", foreign_keys=[approver_role_id]
    )

    def __repr__(self) -> str:
        return f"<ApprovalWorkflowStep level={self.level} approver={self.approver_role_id}>"


class ApprovalInstance(Base):
    __tablename__ = "approval_instances"

    __table_args__ = (
        Index("ix_approval_instances_module_target", "module_type", "target_id"),
        Index("ix_approval_instances_assigned_approver_id", "assigned_approver_id"),
        Index("ix_approval_instances_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_approver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    actioned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    actioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit fields
    resolved_by_scope: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_approver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workflow: Mapped[ApprovalWorkflow] = relationship(
        "ApprovalWorkflow", back_populates="instances"
    )
    approver_role: Mapped["Role"] = relationship("Role", foreign_keys=[approver_role_id])
    assigned_approver: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[assigned_approver_id]
    )
    actioned_by: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[actioned_by_id]
    )
    resolved_approver: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[resolved_approver_id]
    )

    def __repr__(self) -> str:
        return f"<ApprovalInstance level={self.level} status={self.status} target={self.target_id}>"
