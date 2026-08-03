from typing import Literal, Union, Optional, Annotated
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime

# Config schemas for each connection type
class DirectDeviceConfig(BaseModel):
    connection_type: Literal["DIRECT"] = "DIRECT"
    ip_address: str = Field(..., description="Device IP address")
    port: int = Field(default=4370, ge=1, le=65535)
    password: str = Field(default="", description="Device communication password")
    timeout_seconds: int = Field(default=10, ge=1, le=120)
    auto_sync: bool = False
    sync_interval_minutes: int = Field(default=30, ge=1, le=1440)

class DatabaseConfig(BaseModel):
    connection_type: Literal["DATABASE"] = "DATABASE"
    db_type: str = Field(default="mysql", description="mysql, mssql, postgresql")
    host: str
    port: int = Field(default=3306)
    database: str
    username: str
    password: str
    use_ssl: bool = False

class RestAPIConfig(BaseModel):
    connection_type: Literal["REST_API"] = "REST_API"
    base_url: str
    auth_type: str = Field(default="token", description="token, basic, apikey")
    token: str = ""
    custom_headers: dict = Field(default_factory=dict)

class AdmsPushConfig(BaseModel):
    connection_type: Literal["ADMS_PUSH"] = "ADMS_PUSH"
    receiver_endpoint: str = "/biometric/adms/push"
    secret_key: str = ""

ConnectionConfig = Annotated[
    Union[DirectDeviceConfig, DatabaseConfig, RestAPIConfig, AdmsPushConfig],
    Field(discriminator="connection_type")
]

class BmConnectionProfileCreate(BaseModel):
    device_id: uuid.UUID
    connection_type: str
    config: ConnectionConfig  # Will be encrypted before storage
    is_primary: bool = True

class BmConnectionProfileUpdate(BaseModel):
    config: Optional[ConnectionConfig] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None

class BmConnectionProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    device_id: uuid.UUID
    connection_type: str
    is_primary: bool
    is_active: bool
    # Config returned WITHOUT sensitive fields (passwords masked)
    config_summary: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
