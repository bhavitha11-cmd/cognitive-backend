"""
Normalization Service

Converts raw vendor-specific attendance records into normalized log entries.
All downstream consumers (Attendance Engine, Reports) only see normalized logs.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.biometric.bm_raw_log import BmRawLog
from app.models.biometric.bm_normalized_log import BmNormalizedLog
from app.models.biometric.bm_employee_mapping import BmEmployeeMapping

logger = logging.getLogger(__name__)

@dataclass
class NormalizationResult:
    normalized: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list = None
    
    def __post_init__(self):
        if self.error_details is None:
            self.error_details = []


class NormalizationService:
    """
    Normalizes raw biometric attendance records into ERP-compatible format.
    
    Design principle: The Attendance module NEVER reads from bm_raw_logs.
    It only consumes bm_normalized_logs through service interfaces.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def normalize_raw_log(self, raw_log: BmRawLog) -> Optional[BmNormalizedLog]:
        """
        Normalize a single raw log into a normalized log entry.
        Unmapped logs are preserved with processing_status='UNMAPPED'.
        """
        # Skip duplicates
        if raw_log.is_duplicate:
            return None
        
        employee_id = None
        mapping = None
        if raw_log.employee_mapping_id:
            mapping = self.db.scalar(
                select(BmEmployeeMapping).where(BmEmployeeMapping.id == raw_log.employee_mapping_id)
            )
        if not mapping and raw_log.device_user_id:
            mapping = self.db.scalar(
                select(BmEmployeeMapping).where(
                    BmEmployeeMapping.device_id == raw_log.device_id,
                    BmEmployeeMapping.biometric_user_id == raw_log.device_user_id,
                    BmEmployeeMapping.is_active == True
                )
            )
            if mapping:
                raw_log.employee_mapping_id = mapping.id

        if mapping and mapping.is_active:
            employee_id = mapping.employee_id

        # Normalize punch type
        normalized_punch_type = self._normalize_punch_type(raw_log.punch_type, raw_log.verification_type)
        status = "PENDING" if employee_id else "UNMAPPED"

        # Check if already normalized
        existing = self.db.scalar(
            select(BmNormalizedLog).where(BmNormalizedLog.raw_log_id == raw_log.id)
        )
        if existing:
            if existing.employee_id != employee_id or existing.processing_status != status:
                existing.employee_id = employee_id
                existing.processing_status = status
                existing.punch_type = normalized_punch_type
                self.db.add(existing)
            return existing

        normalized = BmNormalizedLog(
            raw_log_id=raw_log.id,
            employee_id=employee_id,
            device_id=raw_log.device_id,
            punch_timestamp=raw_log.punch_timestamp,
            punch_type=normalized_punch_type,
            verification_type=raw_log.verification_type,
            processing_status=status,
        )
        self.db.add(normalized)
        return normalized
    
    def batch_normalize(
        self,
        raw_log_ids: list[uuid.UUID],
    ) -> NormalizationResult:
        """Normalize a batch of raw logs."""
        result = NormalizationResult()
        
        raw_logs = list(self.db.scalars(
            select(BmRawLog).where(BmRawLog.id.in_(raw_log_ids))
        ).all())
        
        for raw_log in raw_logs:
            try:
                normalized = self.normalize_raw_log(raw_log)
                if normalized:
                    result.normalized += 1
                else:
                    result.skipped += 1
            except Exception as e:
                result.errors += 1
                result.error_details.append({"raw_log_id": str(raw_log.id), "error": str(e)})
                logger.error(f"[Normalization] Failed to normalize raw_log {raw_log.id}: {e}")
        
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"[Normalization] Commit failed: {e}")
            raise
        
        return result
    
    def _normalize_punch_type(self, punch_type: Optional[str], verification_type: Optional[str]) -> str:
        """Map device punch types to normalized ERP punch types."""
        if punch_type == "IN":
            return "IN"
        elif punch_type == "OUT":
            return "OUT"
        else:
            return "UNKNOWN"
