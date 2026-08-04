"""
Sync History Service

Manages querying sync histories.
"""
import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.biometric.bm_sync_history import BmSyncHistory

logger = logging.getLogger(__name__)


class SyncHistoryService:
    def __init__(self, db: Session):
        self.db = db
        
    def list_history(
        self,
        device_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BmSyncHistory], int]:
        q = select(BmSyncHistory)
        
        if device_id:
            q = q.where(BmSyncHistory.device_id == device_id)
        if status:
            q = q.where(BmSyncHistory.status == status)
            
        # Auto-cleanup stale RUNNING records older than 3 minutes
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
        stale_records = list(self.db.scalars(
            select(BmSyncHistory).where(
                BmSyncHistory.status == "RUNNING",
                BmSyncHistory.started_at < cutoff
            )
        ).all())
        if stale_records:
            for s in stale_records:
                s.status = "CANCELLED"
                s.error_message = "Sync timed out or process was restarted"
            self.db.commit()

        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        q = q.order_by(BmSyncHistory.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
        
        return list(self.db.scalars(q).all()), total

    def get_history(self, history_id: uuid.UUID) -> Optional[BmSyncHistory]:
        return self.db.scalar(
            select(BmSyncHistory).where(BmSyncHistory.id == history_id)
        )
        
    def retry_failed_sync(self, history_id: uuid.UUID, sync_engine) -> dict:
        history = self.get_history(history_id)
        if not history:
            raise ValueError("History not found")
        
        return sync_engine.run_sync(
            device_id=history.device_id,
            sync_type="RETRY",
        )
