from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
import uuid

class BmRawLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    device_id: uuid.UUID
    device_user_id: str
    punch_timestamp: datetime
    verification_type: Optional[str] = None
    punch_type: Optional[str] = None
    source: str
    received_at: datetime
    is_duplicate: bool
    
    # Joined
    device_name: Optional[str] = None
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None

class BmNormalizedLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    raw_log_id: uuid.UUID
    employee_id: uuid.UUID
    device_id: uuid.UUID
    punch_timestamp: datetime
    punch_type: str
    verification_type: Optional[str] = None
    normalized_at: datetime
    processing_status: str
    error_message: Optional[str] = None
    
    # Joined fields
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department_name: Optional[str] = None
    device_name: Optional[str] = None

class BmLogFilterParams(BaseModel):
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    organization_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None
    employee_id: Optional[uuid.UUID] = None
    device_id: Optional[uuid.UUID] = None
    verification_type: Optional[str] = None
    punch_type: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
