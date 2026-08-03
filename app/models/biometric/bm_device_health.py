from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class BmDeviceHealth(Base):
    __tablename__ = "bm_device_health"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bm_devices.id", ondelete="CASCADE"), unique=True, nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    storage_used_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    registered_users_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connection_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN", nullable=False)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_health_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    device: Mapped["BmDevice"] = relationship("BmDevice", back_populates="health_record")
