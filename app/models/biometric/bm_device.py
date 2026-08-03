from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class BmDevice(Base):
    __tablename__ = "bm_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    vendor: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, default="ACTIVE", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, index=True, default=True, nullable=False)
    
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connection_profiles: Mapped[list["BmConnectionProfile"]] = relationship("BmConnectionProfile", back_populates="device", cascade="all, delete-orphan")
    employee_mappings: Mapped[list["BmEmployeeMapping"]] = relationship("BmEmployeeMapping", back_populates="device", cascade="all, delete-orphan")
    raw_logs: Mapped[list["BmRawLog"]] = relationship("BmRawLog", back_populates="device")
    sync_history: Mapped[list["BmSyncHistory"]] = relationship("BmSyncHistory", back_populates="device", cascade="all, delete-orphan")
    health_record: Mapped["BmDeviceHealth"] = relationship("BmDeviceHealth", back_populates="device", uselist=False, cascade="all, delete-orphan")
    sync_config: Mapped["BmSyncConfig"] = relationship("BmSyncConfig", back_populates="device", uselist=False, cascade="all, delete-orphan")
