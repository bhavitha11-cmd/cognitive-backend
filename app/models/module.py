from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Module(Base):
    """Registry table for top-level ERP modules (e.g. Projects, HR, Settings).

    This table is the authoritative source for what modules exist in the system.
    The permission matrix UI, sidebar navigation, and authorization engine all
    read from this table dynamically.
    """

    __tablename__ = "modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_key: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    module_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    icon: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    features: Mapped[list["Feature"]] = relationship(
        "Feature", back_populates="module", cascade="all, delete-orphan",
        order_by="Feature.display_order"
    )

    def __repr__(self) -> str:
        return f"<Module {self.module_key}>"
