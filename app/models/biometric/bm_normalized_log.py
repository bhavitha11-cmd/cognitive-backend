from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class BmNormalizedLog(Base):
    __tablename__ = "bm_normalized_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bm_raw_logs.id", ondelete="RESTRICT"), unique=True, nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bm_devices.id", ondelete="RESTRICT"), index=True, nullable=False)
    punch_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    punch_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    verification_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    normalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), index=True, default="PENDING", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attendance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_bm_norm_logs_emp_time", "employee_id", "punch_timestamp"),
    )
