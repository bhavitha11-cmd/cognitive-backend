from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Feature(Base):
    """Registry table for child features under each module.

    Examples: 'tasks' under Projects, 'employees' under HR, 'roles' under Settings.
    This table drives the permission matrix, sidebar navigation, breadcrumbs, and
    the authorization engine. When a new ERP feature is added, an administrator
    simply inserts a record here — no code changes required.
    """

    __tablename__ = "features"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modules.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    feature_key: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    feature_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    route: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    icon: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    menu_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Show this feature in the sidebar navigation"
    )
    permission_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Include this feature in the permission matrix"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="System features cannot be deactivated by admins"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    module: Mapped["Module"] = relationship(
        "Module", back_populates="features"
    )
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="feature", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Feature {self.feature_key}>"
