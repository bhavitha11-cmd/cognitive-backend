from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.core.permission_scope import PermissionScope


class RolePermission(Base):
    """Scope-based permission for a specific feature within a role.

    Each row defines the data access scope (NONE, OWNED, ADDED, ADDED_OWNED,
    TEAM, DEPARTMENT, COMPANY, ALL) for each CRUD action on a feature.
    """

    __tablename__ = "role_permissions"

    __table_args__ = (
        UniqueConstraint(
            "role_id", "feature_id", name="uq_role_feature"
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
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # --- Legacy column kept for migration compatibility ---
    module_name: Mapped[str | None] = mapped_column(
        String(50), index=True, nullable=True
    )

    # --- Scope-based permission fields ---
    view_scope: Mapped[str] = mapped_column(
        String(50), default=PermissionScope.NONE.value, nullable=False,
        server_default=PermissionScope.NONE.value,
    )
    create_scope: Mapped[str] = mapped_column(
        String(50), default=PermissionScope.NONE.value, nullable=False,
        server_default=PermissionScope.NONE.value,
    )
    update_scope: Mapped[str] = mapped_column(
        String(50), default=PermissionScope.NONE.value, nullable=False,
        server_default=PermissionScope.NONE.value,
    )
    delete_scope: Mapped[str] = mapped_column(
        String(50), default=PermissionScope.NONE.value, nullable=False,
        server_default=PermissionScope.NONE.value,
    )

    # Relationships
    role: Mapped["Role"] = relationship(
        "Role", back_populates="permissions"
    )
    feature: Mapped["Feature"] = relationship(
        "Feature", back_populates="role_permissions"
    )

    # ── Backward-compatible computed properties ──────────────────────────────
    # These properties allow existing code that checks `perm.can_view`, etc.
    # to continue working without modification.

    @property
    def can_view(self) -> bool:
        return PermissionScope.has_access(self.view_scope)

    @property
    def can_create(self) -> bool:
        return PermissionScope.has_access(self.create_scope)

    @property
    def can_edit(self) -> bool:
        return PermissionScope.has_access(self.update_scope)

    @property
    def can_activate(self) -> bool:
        return PermissionScope.has_access(self.delete_scope)

    def __repr__(self) -> str:
        feat_key = self.feature.feature_key if self.feature else self.module_name
        return f"<RolePermission {feat_key}>"
