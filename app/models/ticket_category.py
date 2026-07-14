from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class TicketCategory(Base):
    __tablename__ = "ticket_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    types: Mapped[list["TicketType"]] = relationship(
        "TicketType", back_populates="category", cascade="all, delete-orphan"
    )
    handlers: Mapped[list["TicketCategoryHandler"]] = relationship(
        "TicketCategoryHandler", back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TicketCategory {self.name}>"
