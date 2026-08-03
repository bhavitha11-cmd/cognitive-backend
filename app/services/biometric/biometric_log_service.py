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
    ) -> tuple[list[dict], int]:
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
        
        logs = list(self.db.scalars(q).all())
        result_logs = []
        for log in logs:
            emp_name = None
            emp_code = None
            if log.employee:
                emp_name = f"{log.employee.first_name or ''} {log.employee.last_name or ''}".strip()
                emp_code = log.employee.employee_code
            
            device_name = log.device.device_name if log.device else None
            
            result_logs.append({
                "id": str(log.id),
                "punch_timestamp": log.punch_timestamp.isoformat() if log.punch_timestamp else None,
                "punch_type": log.punch_type,
                "verification_type": log.verification_type,
                "processing_status": log.processing_status,
                "employee_id": str(log.employee_id) if log.employee_id else None,
                "employee_name": emp_name or "Unassigned",
                "employee_code": emp_code or "-",
                "device_id": str(log.device_id) if log.device_id else None,
                "device_name": device_name or "Biometric Device",
            })
            
        return result_logs, total

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
        writer.writerow(["Log ID", "Employee Code", "Employee Name", "Device Name", "Punch Time", "Punch Type", "Verification", "Status"])
        for log in logs:
            writer.writerow([
                log.get("id", ""),
                log.get("employee_code", ""),
                log.get("employee_name", ""),
                log.get("device_name", ""),
                log.get("punch_timestamp", ""),
                log.get("punch_type", ""),
                log.get("verification_type", ""),
                log.get("processing_status", ""),
            ])
        return output.getvalue()
