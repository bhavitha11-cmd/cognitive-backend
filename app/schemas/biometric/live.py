from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

class BmLiveAttendanceRecord(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    department_name: Optional[str] = None
    current_status: str  # IN, OUT, NOT_PUNCHED
    last_punch_time: Optional[datetime] = None
    last_punch_type: Optional[str] = None
    device_name: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    verification_mode: Optional[str] = None
    branch: Optional[str] = None
