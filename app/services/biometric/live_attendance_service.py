"""
Live Attendance Service

Provides live attendance dashboard views (current IN/OUT status).
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.biometric.bm_normalized_log import BmNormalizedLog

logger = logging.getLogger(__name__)

class LiveAttendanceService:
    def __init__(self, db: Session):
        self.db = db
        
    def get_live_attendance(self, organization_id: uuid.UUID, department_id: uuid.UUID = None, branch: str = None) -> list[dict]:
        # A basic implementation fetching today's logs and grouping by employee
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        q = select(BmNormalizedLog).where(BmNormalizedLog.punch_timestamp >= today)
        # Note: in real implementation, you would join with Employee and filter by org, dept, branch
        
        logs = self.db.scalars(q.order_by(desc(BmNormalizedLog.punch_timestamp))).all()
        
        status_map = {}
        for log in logs:
            if not log.employee_id:
                continue
            if log.employee_id not in status_map:
                status_map[log.employee_id] = {
                    "employee_id": str(log.employee_id),
                    "last_punch_time": log.punch_timestamp,
                    "last_punch_type": log.punch_type,
                    "device_id": str(log.device_id),
                    "current_status": "IN" if log.punch_type == "IN" else "OUT"
                }
                
        # Fill in employees who haven't punched
        # ... logic to fetch all active employees in scope ...
        
        result = list(status_map.values())
        result.sort(key=lambda x: x["last_punch_time"], reverse=True)
        return result
