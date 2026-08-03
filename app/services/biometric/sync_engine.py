"""
Sync Engine — orchestrates the complete biometric data sync lifecycle.

Design:
  1. Acquire Redis distributed lock (prevents concurrent sync for same device)
  2. Create SyncHistory record (status=RUNNING)
  3. Fetch records from connector
  4. Deduplicate against existing raw logs
  5. Persist new raw logs (immutable)
  6. Resolve employee mappings
  7. Normalize records
  8. Update checkpoint (for incremental sync)
  9. Update SyncHistory (SUCCESS/PARTIAL/FAILED)
  10. Update DeviceHealth
  11. Release Redis lock
"""
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models.biometric.bm_device import BmDevice
from app.models.biometric.bm_raw_log import BmRawLog
from app.models.biometric.bm_sync_history import BmSyncHistory
from app.models.biometric.bm_device_health import BmDeviceHealth
from app.models.biometric.bm_employee_mapping import BmEmployeeMapping
from app.models.biometric.bm_sync_config import BmSyncConfig
from app.services.biometric.connectors.factory import ConnectorFactory
from app.services.biometric.normalization_service import NormalizationService
from app.services.biometric.connection_profile_service import ConnectionProfileService

logger = logging.getLogger(__name__)

@dataclass
class SyncResult:
    device_id: uuid.UUID
    sync_history_id: Optional[uuid.UUID] = None
    status: str = "SUCCESS"
    records_read: int = 0
    records_saved: int = 0
    duplicates_found: int = 0
    errors_count: int = 0
    normalized_count: int = 0
    error_message: Optional[str] = None
    duration_seconds: float = 0.0


class SyncEngine:
    """
    Enterprise sync engine supporting manual, scheduled, incremental,
    and retry sync modes with distributed locking via Redis.
    """
    
    LOCK_TTL_SECONDS = 300  # 5 minutes max lock duration
    
    def __init__(self, db: Session):
        self.db = db
        self._redis = None
    
    def _get_redis(self):
        if not self._redis:
            try:
                from app.core.redis import redis_client
                self._redis = redis_client
            except ImportError:
                pass
        return self._redis
    
    def _acquire_lock(self, device_id: uuid.UUID) -> bool:
        """Acquire Redis distributed lock for this device sync."""
        lock_key = f"biometric:sync:lock:{device_id}"
        try:
            r = self._get_redis()
            if r:
                result = r.set(lock_key, "1", nx=True, ex=self.LOCK_TTL_SECONDS)
                return bool(result)
        except Exception as e:
            logger.warning(f"[SyncEngine] Redis lock unavailable (non-fatal): {e}")
        return True  # Allow sync even without Redis
    
    def _release_lock(self, device_id: uuid.UUID) -> None:
        """Release Redis distributed lock."""
        lock_key = f"biometric:sync:lock:{device_id}"
        try:
            r = self._get_redis()
            if r:
                r.delete(lock_key)
        except Exception as e:
            logger.warning(f"[SyncEngine] Failed to release lock: {e}")
    
    def run_sync(
        self,
        device_id: uuid.UUID,
        sync_type: str = "MANUAL",
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        triggered_by: Optional[uuid.UUID] = None,
    ) -> SyncResult:
        """Execute a full sync for the given device."""
        import time
        start_time = time.time()
        
        result = SyncResult(device_id=device_id)
        
        # Check lock
        if not self._acquire_lock(device_id):
            result.status = "FAILED"
            result.error_message = "Sync already running for this device"
            return result
        
        # Create sync history record
        sync_history = BmSyncHistory(
            device_id=device_id,
            sync_type=sync_type,
            started_at=datetime.now(timezone.utc),
            status="RUNNING",
            triggered_by=triggered_by,
        )
        self.db.add(sync_history)
        self.db.commit()
        result.sync_history_id = sync_history.id
        
        try:
            # Get device
            device = self.db.scalar(select(BmDevice).where(BmDevice.id == device_id))
            if not device:
                raise ValueError(f"Device {device_id} not found")
            
            # Determine time window
            if not to_dt:
                to_dt = datetime.now(timezone.utc)
            if not from_dt:
                # Use sync config lookback or default 24h
                sync_config = self.db.scalar(
                    select(BmSyncConfig).where(BmSyncConfig.device_id == device_id)
                )
                lookback_days = sync_config.lookback_days if sync_config else 1
                
                # For incremental: use last sync checkpoint
                if sync_type == "INCREMENTAL" and sync_history:
                    last_sync = self.db.scalar(
                        select(BmSyncHistory)
                        .where(
                            BmSyncHistory.device_id == device_id,
                            BmSyncHistory.status == "SUCCESS",
                            BmSyncHistory.id != sync_history.id,
                        )
                        .order_by(BmSyncHistory.started_at.desc())
                    )
                    if last_sync and last_sync.checkpoint_data:
                        checkpoint = last_sync.checkpoint_data
                        if "last_punch_timestamp" in checkpoint:
                            from_dt = datetime.fromisoformat(checkpoint["last_punch_timestamp"])
                
                if not from_dt:
                    from_dt = to_dt - timedelta(days=lookback_days)
            
            # Get connection profile and create connector
            profile_service = ConnectionProfileService(self.db)
            profile = profile_service.get_profile_for_device(device_id)
            if not profile:
                raise ValueError(f"No active connection profile for device {device_id}")
            
            connector = ConnectorFactory.get_connector(
                device.vendor,
                profile.connection_type,
                profile.config_encrypted,
            )
            
            # Fetch records from device
            with connector:
                raw_records = connector.fetch_attendance(from_dt, to_dt)
            
            result.records_read = len(raw_records)
            logger.info(f"[SyncEngine] Device {device.device_name}: fetched {len(raw_records)} records")
            
            # Get sync config for batch size
            sync_cfg = self.db.scalar(
                select(BmSyncConfig).where(BmSyncConfig.device_id == device_id)
            )
            batch_size = sync_cfg.batch_size if sync_cfg else 500
            
            # Process in batches
            new_raw_log_ids = []
            last_punch_timestamp = None
            
            for i in range(0, len(raw_records), batch_size):
                batch = raw_records[i:i + batch_size]
                
                for record in batch:
                    # Check for duplicate
                    existing = self.db.scalar(
                        select(BmRawLog).where(
                            BmRawLog.device_id == device_id,
                            BmRawLog.device_user_id == record.device_user_id,
                            BmRawLog.punch_timestamp == record.punch_timestamp,
                        )
                    )
                    
                    if existing:
                        result.duplicates_found += 1
                        continue
                    
                    # Find employee mapping
                    mapping = self.db.scalar(
                        select(BmEmployeeMapping).where(
                            BmEmployeeMapping.device_id == device_id,
                            BmEmployeeMapping.biometric_user_id == record.device_user_id,
                            BmEmployeeMapping.is_active == True,
                        )
                    )
                    
                    # Create raw log (immutable)
                    raw_log = BmRawLog(
                        device_id=device_id,
                        employee_mapping_id=mapping.id if mapping else None,
                        device_user_id=record.device_user_id,
                        punch_timestamp=record.punch_timestamp,
                        verification_type=record.verification_type,
                        punch_type=record.punch_type,
                        raw_payload=record.raw_data,
                        source="SYNC",
                        sync_history_id=sync_history.id,
                        is_duplicate=False,
                    )
                    self.db.add(raw_log)
                    self.db.flush()
                    new_raw_log_ids.append(raw_log.id)
                    result.records_saved += 1
                    
                    if last_punch_timestamp is None or record.punch_timestamp > last_punch_timestamp:
                        last_punch_timestamp = record.punch_timestamp
            
            self.db.commit()
            
            # Normalize all new records
            if new_raw_log_ids:
                norm_service = NormalizationService(self.db)
                norm_result = norm_service.batch_normalize(new_raw_log_ids)
                result.normalized_count = norm_result.normalized
                result.errors_count = norm_result.errors
            
            # Update checkpoint
            checkpoint = {}
            if last_punch_timestamp:
                checkpoint["last_punch_timestamp"] = last_punch_timestamp.isoformat()
                checkpoint["records_synced"] = result.records_saved
            
            # Determine final status
            if result.errors_count > 0 and result.records_saved > 0:
                status = "PARTIAL"
            elif result.errors_count > 0:
                status = "FAILED"
            else:
                status = "SUCCESS"
            
            result.status = status
            result.duration_seconds = time.time() - start_time
            
            # Update sync history
            sync_history.ended_at = datetime.now(timezone.utc)
            sync_history.status = status
            sync_history.records_read = result.records_read
            sync_history.records_saved = result.records_saved
            sync_history.duplicates_found = result.duplicates_found
            sync_history.errors_count = result.errors_count
            sync_history.checkpoint_data = checkpoint
            sync_history.duration_seconds = result.duration_seconds
            
            # Update device health
            self._update_device_health(device_id, "ONLINE", None)
            
            # Update device last_sync_at
            device.last_sync_at = datetime.now(timezone.utc)
            device.last_seen_at = datetime.now(timezone.utc)
            
            self.db.commit()
            logger.info(f"[SyncEngine] Sync complete for {device.device_name}: {status}")
            
        except Exception as e:
            self.db.rollback()
            error_msg = str(e)
            logger.error(f"[SyncEngine] Sync failed for device {device_id}: {error_msg}")
            
            result.status = "FAILED"
            result.error_message = error_msg
            result.duration_seconds = time.time() - start_time
            
            try:
                sync_history.ended_at = datetime.now(timezone.utc)
                sync_history.status = "FAILED"
                sync_history.error_message = error_msg[:2000]
                sync_history.duration_seconds = result.duration_seconds
                self._update_device_health(device_id, "OFFLINE", error_msg)
                self.db.commit()
            except Exception:
                self.db.rollback()
        
        finally:
            self._release_lock(device_id)
        
        return result
    
    def _update_device_health(self, device_id: uuid.UUID, status: str, error: Optional[str]) -> None:
        """Update or create device health record."""
        health = self.db.scalar(
            select(BmDeviceHealth).where(BmDeviceHealth.device_id == device_id)
        )
        if health:
            health.connection_status = status
            health.last_checked_at = datetime.now(timezone.utc)
            if status == "ONLINE":
                health.last_successful_sync_at = datetime.now(timezone.utc)
                health.last_error = None
            elif error:
                health.last_error = error[:2000]
