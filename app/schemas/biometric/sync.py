from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
import uuid

class BmSyncTriggerRequest(BaseModel):
    sync_type: str = Field(default="MANUAL", description="MANUAL, INCREMENTAL")
    from_datetime: Optional[datetime] = None
    to_datetime: Optional[datetime] = None

class BmSyncHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    device_id: uuid.UUID
    device_name: Optional[str] = None
    sync_type: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    records_read: int
    records_saved: int
    duplicates_found: int
    errors_count: int
    status: str
    error_message: Optional[str] = None
    retry_count: int
    duration_seconds: Optional[float] = None

class BmSyncConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    device_id: uuid.UUID
    is_auto_sync: bool
    sync_interval_minutes: int
    sync_schedule: Optional[str] = None
    batch_size: int
    lookback_days: int
    is_active: bool

class BmSyncConfigUpdate(BaseModel):
    is_auto_sync: Optional[bool] = None
    sync_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    sync_schedule: Optional[str] = None
    batch_size: Optional[int] = Field(None, ge=1, le=5000)
    lookback_days: Optional[int] = Field(None, ge=1, le=90)
    is_active: Optional[bool] = None
