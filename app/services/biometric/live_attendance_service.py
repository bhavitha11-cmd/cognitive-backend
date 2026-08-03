"""
Live Attendance Service

Provides live attendance dashboard views (current IN/OUT status).
Shows the most recent punch for each employee today.
"""
import uuid
import logging
from datetime import datetime, timezone
from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.biometric.bm_normalized_log import BmNormalizedLog
from app.models.employee import Employee
from app.models.biometric.bm_device import BmDevice

logger = logging.getLogger(__name__)

class LiveAttendanceService:
    def __init__(self, db: Session):
        self.db = db
        
    def get_live_attendance(
        self,
        target_date: Optional[date] = None,
        organization_id: Optional[uuid.UUID] = None,
        department_id: Optional[uuid.UUID] = None,
        branch: Optional[str] = None,
    ) -> list[dict]:
        """
        Returns live attendance metrics for each employee for a given target date (defaults to today).
        Includes first_in_time, last_punch_time, total_in_time, total_out_time,
        and remaining time to complete the required 8-hour shift.
        """
        from app.core.org_time import get_org_today_range
        from sqlalchemy import asc

        start_utc, end_utc = get_org_today_range(target_date)
        now_utc = datetime.now(timezone.utc)

        # Fetch all normalized logs for target date in organization timezone, ascending
        q = (
            select(BmNormalizedLog)
            .where(
                BmNormalizedLog.punch_timestamp >= start_utc,
                BmNormalizedLog.punch_timestamp <= end_utc,
            )
            .order_by(asc(BmNormalizedLog.punch_timestamp))
        )
        logs = self.db.scalars(q).all()

        if not logs and target_date is None:
            # Fallback for initial demo/dev environment when today has no logs
            q = select(BmNormalizedLog).order_by(asc(BmNormalizedLog.punch_timestamp)).limit(500)
            logs = self.db.scalars(q).all()

        # Group logs by employee_id
        emp_logs: dict[uuid.UUID, list[BmNormalizedLog]] = {}
        for log in logs:
            if log.employee_id:
                emp_logs.setdefault(log.employee_id, []).append(log)

        result = []
        target_work_seconds = 8 * 3600  # 8 hours policy = 28,800 seconds

        for emp_id, elogs in emp_logs.items():
            emp = elogs[0].employee if elogs[0].employee else self.db.get(Employee, emp_id)
            device = elogs[-1].device

            emp_name = ""
            emp_code = ""
            if emp:
                first = (emp.first_name or "").strip()
                last = (emp.last_name or "").strip()
                emp_name = f"{first} {last}".strip() or emp.employee_code
                emp_code = emp.employee_code or ""

            device_name = device.device_name if device else "Biometric Device"

            first_in_log = elogs[0]
            last_punch_log = elogs[-1]

            current_status = "IN" if last_punch_log.punch_type == "IN" else "OUT"

            # Calculate total inside time
            total_in_seconds = 0
            in_start = None

            for l in elogs:
                ptype = (l.punch_type or "IN").upper()
                if ptype == "IN":
                    if in_start is None:
                        in_start = l.punch_timestamp
                elif ptype == "OUT":
                    if in_start is not None:
                        total_in_seconds += int((l.punch_timestamp - in_start).total_seconds())
                        in_start = None

            if in_start is not None:
                eff_end = min(now_utc, end_utc)
                if eff_end > in_start:
                    total_in_seconds += int((eff_end - in_start).total_seconds())

            eff_last = max(last_punch_log.punch_timestamp, now_utc) if current_status == "IN" else last_punch_log.punch_timestamp
            total_elapsed_seconds = int((eff_last - first_in_log.punch_timestamp).total_seconds())
            total_out_seconds = max(0, total_elapsed_seconds - total_in_seconds)

            remaining_seconds = max(0, target_work_seconds - total_in_seconds)

            in_h, in_m = total_in_seconds // 3600, (total_in_seconds % 3600) // 60
            out_h, out_m = total_out_seconds // 3600, (total_out_seconds % 3600) // 60
            rem_h, rem_m = remaining_seconds // 3600, (remaining_seconds % 3600) // 60

            total_in_formatted = f"{in_h}h {in_m:02d}m"
            total_out_formatted = f"{out_h}h {out_m:02d}m"
            remaining_formatted = f"{rem_h}h {rem_m:02d}m remaining" if remaining_seconds > 0 else "Completed (8h)"

            today_punches_list = [
                {
                    "punch_time": l.punch_timestamp.isoformat(),
                    "punch_type": l.punch_type,
                    "verification_type": l.verification_type,
                }
                for l in elogs
            ]

            result.append({
                "employee_id": str(emp_id),
                "employee_name": emp_name,
                "employee_code": emp_code,
                "department_name": None,
                "current_status": current_status,
                "first_in_time": first_in_log.punch_timestamp.isoformat() if first_in_log.punch_timestamp else None,
                "last_punch_time": last_punch_log.punch_timestamp.isoformat() if last_punch_log.punch_timestamp else None,
                "last_punch_type": last_punch_log.punch_type,
                "total_in_seconds": total_in_seconds,
                "total_in_time_formatted": total_in_formatted,
                "total_out_seconds": total_out_seconds,
                "total_out_time_formatted": total_out_formatted,
                "remaining_seconds": remaining_seconds,
                "remaining_time_formatted": remaining_formatted,
                "target_work_hours": 8.0,
                "is_shift_completed": remaining_seconds == 0,
                "today_punches_count": len(elogs),
                "today_punches_list": today_punches_list,
                "device_name": device_name,
                "device_id": str(last_punch_log.device_id) if last_punch_log.device_id else None,
                "verification_mode": last_punch_log.verification_type,
                "branch": branch,
            })

        result.sort(key=lambda x: x["last_punch_time"] or "", reverse=True)
        return result
