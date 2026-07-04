from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"

    __table_args__ = (
        UniqueConstraint(
            "role_id", "module_name", name="uq_role_module"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    module_name: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False
    )
    can_view: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    can_create: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    can_edit: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    can_activate: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    role: Mapped["Role"] = relationship(
        "Role", back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<RolePermission {self.module_name}>"
