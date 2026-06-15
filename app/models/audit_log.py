from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_performed_by", "performed_by"),
        Index("ix_audit_logs_performed_at", "performed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    old_value: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    new_value: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    performer: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[performed_by]
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.entity_type}#{self.entity_id}: {self.action}>"
