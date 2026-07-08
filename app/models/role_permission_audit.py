from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class RolePermissionAudit(Base):
    """Audit trail for every permission scope change.

    When an administrator modifies a role's permission (e.g. changes the view
    scope of Tasks from NONE to TEAM), a record is inserted here capturing the
    old and new scope values along with who made the change and when.
    """

    __tablename__ = "role_permission_audits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Permission action: view, create, update, delete"
    )
    old_scope: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    new_scope: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", foreign_keys=[role_id])
    feature: Mapped["Feature"] = relationship("Feature", foreign_keys=[feature_id])
    changed_by_employee: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[changed_by]
    )

    def __repr__(self) -> str:
        return f"<RolePermissionAudit role={self.role_id} feature={self.feature_id} {self.action}: {self.old_scope}->{self.new_scope}>"
