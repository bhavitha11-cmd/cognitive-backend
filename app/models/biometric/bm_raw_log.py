from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class BmRawLog(Base):
    """
    Table: bm_raw_logs - IMMUTABLE (never update or delete)
    """
    __tablename__ = "bm_raw_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bm_devices.id", ondelete="RESTRICT"), nullable=False)
    employee_mapping_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bm_employee_mappings.id", ondelete="SET NULL"), nullable=True)
    device_user_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    punch_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    verification_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    punch_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="SYNC", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, index=True, default=False, nullable=False)
    sync_history_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bm_sync_history.id", ondelete="SET NULL"), index=True, nullable=True)

    __table_args__ = (
        UniqueConstraint("device_id", "device_user_id", "punch_timestamp", name="uq_bm_raw_log_unique_punch"),
        Index("ix_bm_raw_logs_device_timestamp", "device_id", "punch_timestamp"),
    )

    device: Mapped["BmDevice"] = relationship("BmDevice", back_populates="raw_logs")
    sync_history: Mapped["BmSyncHistory"] = relationship("BmSyncHistory", back_populates="raw_logs")
