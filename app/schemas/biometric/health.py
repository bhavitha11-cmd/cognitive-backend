from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
import uuid

class BmDeviceHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    device_id: uuid.UUID
    device_name: Optional[str] = None
    firmware_version: Optional[str] = None
    storage_used_pct: Optional[float] = None
    registered_users_count: Optional[int] = None
    connection_status: str
    last_successful_sync_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_checked_at: datetime
    response_time_ms: Optional[int] = None

class ConnectionTestResult(BaseModel):
    status: str  # connected, failed
    device_model: Optional[str] = None
    firmware_version: Optional[str] = None
    device_time: Optional[datetime] = None
    registered_users: Optional[int] = None
    last_attendance_time: Optional[datetime] = None
    response_time_ms: Optional[float] = None
    error_code: Optional[str] = None
    message: str
    suggestions: list[str] = []
