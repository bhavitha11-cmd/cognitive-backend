"""
Sync Config Service — manages biometric device synchronization configuration.
"""
import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.biometric.bm_sync_config import BmSyncConfig

logger = logging.getLogger(__name__)


class SyncConfigService:
    def __init__(self, db: Session, current_user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.current_user_id = current_user_id

    def get_config(self, device_id: uuid.UUID) -> Optional[BmSyncConfig]:
        config = self.db.scalar(
            select(BmSyncConfig).where(BmSyncConfig.device_id == device_id)
        )
        if not config:
            # Create default config if none exists for device
            config = BmSyncConfig(
                device_id=device_id,
                is_auto_sync=False,
                sync_interval_minutes=30,
                batch_size=500,
                lookback_days=7,
                is_active=True,
                created_by=self.current_user_id,
                updated_by=self.current_user_id,
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_config(self, device_id: uuid.UUID, data: dict) -> Optional[BmSyncConfig]:
        config = self.get_config(device_id)
        if not config:
            return None

        for key, value in data.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

        config.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(config)
        return config
