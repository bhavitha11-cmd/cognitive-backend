"""
Biometric Log Service

Manages querying and listing raw and normalized logs.
"""
import uuid
import csv
import io
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.biometric.bm_normalized_log import BmNormalizedLog
from app.models.biometric.bm_raw_log import BmRawLog

logger = logging.getLogger(__name__)


class BiometricLogService:
    def __init__(self, db: Session):
        self.db = db
        
    def list_normalized_logs(
        self,
        filters: dict,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BmNormalizedLog], int]:
        q = select(BmNormalizedLog)
        
        if "employee_id" in filters and filters["employee_id"]:
            q = q.where(BmNormalizedLog.employee_id == filters["employee_id"])
        if "device_id" in filters and filters["device_id"]:
            q = q.where(BmNormalizedLog.device_id == filters["device_id"])
        if "punch_type" in filters and filters["punch_type"]:
            q = q.where(BmNormalizedLog.punch_type == filters["punch_type"])
        if "from_date" in filters and filters["from_date"]:
            q = q.where(BmNormalizedLog.punch_timestamp >= filters["from_date"])
        if "to_date" in filters and filters["to_date"]:
            q = q.where(BmNormalizedLog.punch_timestamp <= filters["to_date"])
            
        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        q = q.order_by(BmNormalizedLog.punch_timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
        
        return list(self.db.scalars(q).all()), total

    def list_raw_logs(
        self,
        filters: dict,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BmRawLog], int]:
        q = select(BmRawLog)
        
        if "device_id" in filters and filters["device_id"]:
            q = q.where(BmRawLog.device_id == filters["device_id"])
        if "from_date" in filters and filters["from_date"]:
            q = q.where(BmRawLog.punch_timestamp >= filters["from_date"])
        if "to_date" in filters and filters["to_date"]:
            q = q.where(BmRawLog.punch_timestamp <= filters["to_date"])
            
        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        q = q.order_by(BmRawLog.punch_timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
        
        return list(self.db.scalars(q).all()), total

    def get_log_detail(self, log_id: uuid.UUID) -> Optional[BmNormalizedLog]:
        return self.db.scalar(
            select(BmNormalizedLog).where(BmNormalizedLog.id == log_id)
        )
        
    def export_logs_csv(self, filters: dict) -> str:
        logs, _ = self.list_normalized_logs(filters, page=1, page_size=100000)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Log ID", "Employee ID", "Device ID", "Punch Time", "Punch Type", "Status"])
        for log in logs:
            writer.writerow([
                str(log.id),
                str(log.employee_id) if log.employee_id else "",
                str(log.device_id) if log.device_id else "",
                log.punch_timestamp.isoformat() if log.punch_timestamp else "",
                log.punch_type or "",
                log.processing_status or ""
            ])
        return output.getvalue()
