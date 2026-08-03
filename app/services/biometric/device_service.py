"""
Device Service — manages biometric device CRUD with organization isolation.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update, and_, or_

from app.models.biometric.bm_device import BmDevice
from app.models.biometric.bm_device_health import BmDeviceHealth
from app.models.biometric.bm_sync_config import BmSyncConfig

logger = logging.getLogger(__name__)


class DeviceService:
    def __init__(self, db: Session, current_user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.current_user_id = current_user_id
    
    def create_device(self, data: dict) -> BmDevice:
        device = BmDevice(
            device_name=data["device_name"],
            vendor=data["vendor"].upper(),
            model=data.get("model"),
            serial_number=data.get("serial_number"),
            organization_id=data["organization_id"],
            branch=data.get("branch"),
            timezone=data.get("timezone", "Asia/Kolkata"),
            status=data.get("status", "ACTIVE"),
            description=data.get("description"),
            created_by=self.current_user_id,
            updated_by=self.current_user_id,
        )
        self.db.add(device)
        self.db.flush()
        
        # Auto-create DeviceHealth record
        health = BmDeviceHealth(
            device_id=device.id,
            connection_status="UNKNOWN",
            last_checked_at=datetime.now(timezone.utc),
        )
        self.db.add(health)
        
        # Auto-create SyncConfig with defaults
        sync_config = BmSyncConfig(
            device_id=device.id,
            is_auto_sync=False,
            sync_interval_minutes=30,
            batch_size=500,
            lookback_days=7,
            created_by=self.current_user_id,
        )
        self.db.add(sync_config)
        
        self.db.commit()
        self.db.refresh(device)
        logger.info(f"[DeviceService] Created device {device.device_name} ({device.id})")
        return device
    
    def get_device(self, device_id: uuid.UUID, organization_id: Optional[uuid.UUID] = None) -> Optional[BmDevice]:
        q = select(BmDevice).where(
            BmDevice.id == device_id,
            BmDevice.deleted_at.is_(None),
        )
        if organization_id:
            q = q.where(BmDevice.organization_id == organization_id)
        return self.db.scalar(q)
    
    def list_devices(
        self,
        organization_id: Optional[uuid.UUID] = None,
        vendor: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BmDevice], int]:
        q = select(BmDevice).where(BmDevice.deleted_at.is_(None))
        
        if organization_id:
            q = q.where(BmDevice.organization_id == organization_id)
        if vendor:
            q = q.where(BmDevice.vendor == vendor.upper())
        if status:
            q = q.where(BmDevice.status == status.upper())
        
        # Count
        from sqlalchemy import func
        count_q = select(func.count()).select_from(q.subquery())
        total = self.db.scalar(count_q) or 0
        
        # Paginate
        q = q.order_by(BmDevice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        devices = list(self.db.scalars(q).all())
        
        return devices, total
    
    def update_device(self, device_id: uuid.UUID, data: dict) -> Optional[BmDevice]:
        device = self.get_device(device_id)
        if not device:
            return None
        
        updatable = ["device_name", "vendor", "model", "serial_number", "branch",
                     "timezone", "status", "description", "is_active"]
        for field in updatable:
            if field in data and data[field] is not None:
                setattr(device, field, data[field])
        
        device.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(device)
        return device
    
    def delete_device(self, device_id: uuid.UUID) -> bool:
        device = self.get_device(device_id)
        if not device:
            return False
        device.deleted_at = datetime.now(timezone.utc)
        device.is_active = False
        device.updated_by = self.current_user_id
        self.db.commit()
        return True
