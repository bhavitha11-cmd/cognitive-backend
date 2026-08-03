"""
Device Health Service

Provides device health metrics and updates.
"""
import uuid
import logging
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.biometric.bm_device_health import BmDeviceHealth

logger = logging.getLogger(__name__)


class DeviceHealthService:
    def __init__(self, db: Session):
        self.db = db
        
    def get_health(self, device_id: uuid.UUID) -> Optional[BmDeviceHealth]:
        return self.db.scalar(
            select(BmDeviceHealth).where(BmDeviceHealth.device_id == device_id)
        )
        
    def list_all_health(self, organization_id: Optional[uuid.UUID] = None) -> list[BmDeviceHealth]:
        q = select(BmDeviceHealth)
        # Note: join with Device to filter by org_id in real impl
        return list(self.db.scalars(q).all())
        
    def update_health_from_test(self, device_id: uuid.UUID, test_result: dict) -> BmDeviceHealth:
        health = self.get_health(device_id)
        if not health:
            health = BmDeviceHealth(device_id=device_id)
            self.db.add(health)
            
        health.connection_status = "ONLINE" if test_result.get("success") else "OFFLINE"
        health.last_checked_at = datetime.now(timezone.utc)
        if not test_result.get("success"):
            health.last_error = test_result.get("error")
            
        self.db.commit()
        self.db.refresh(health)
        return health
