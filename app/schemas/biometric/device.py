from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
import uuid

class BmDeviceBase(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=100)
    vendor: str = Field(..., description="ESSL, ZKTECO, MATRIX, SUPREMA, REALTIME, MANTRA")
    model: Optional[str] = None
    serial_number: Optional[str] = None
    organization_id: uuid.UUID = Field(default_factory=lambda: uuid.UUID("00000000-0000-0000-0000-000000000000"))
    branch: Optional[str] = None
    timezone: str = Field(default="Asia/Kolkata")
    status: str = Field(default="ACTIVE", description="ACTIVE, INACTIVE, MAINTENANCE")
    description: Optional[str] = None

class BmDeviceCreate(BmDeviceBase):
    pass

class BmDeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    branch: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class BmDeviceResponse(BmDeviceBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    is_active: bool
    last_sync_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Include health summary if joined
    connection_status: Optional[str] = None
    last_error: Optional[str] = None

class BmDeviceListResponse(BaseModel):
    devices: list[BmDeviceResponse]
    total: int
    page: int
    page_size: int
