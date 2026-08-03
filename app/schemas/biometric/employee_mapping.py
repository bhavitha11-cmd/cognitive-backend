from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
import uuid

class BmEmployeeMappingCreate(BaseModel):
    employee_id: uuid.UUID
    device_id: uuid.UUID
    biometric_user_id: str = Field(..., min_length=1, max_length=50)
    mapping_method: str = Field(default="MANUAL")
    notes: Optional[str] = None

class BmEmployeeMappingUpdate(BaseModel):
    biometric_user_id: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

class BmEmployeeMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    employee_id: uuid.UUID
    device_id: uuid.UUID
    biometric_user_id: str
    mapping_method: str
    is_active: bool
    mapped_at: datetime
    created_at: datetime
    
    # Joined fields from employee
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department_name: Optional[str] = None
    device_name: Optional[str] = None

class BulkMappingItem(BaseModel):
    employee_code: str
    biometric_user_id: str
    device_serial: str

class BmBulkMappingRequest(BaseModel):
    mappings: list[BulkMappingItem]

class BmAutoMappingRequest(BaseModel):
    device_id: uuid.UUID
    match_by: str = Field(default="employee_code", description="employee_code or employee_id")

class BmAutoMappingResult(BaseModel):
    created: int
    skipped: int
    unmatched: list[dict]

class BmEmployeeMappingListResponse(BaseModel):
    mappings: list[BmEmployeeMappingResponse]
    total: int
    page: int
    page_size: int

# Alias used by router
BmAutoMapRequest = BmAutoMappingRequest
