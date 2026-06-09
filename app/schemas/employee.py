import uuid
from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

VALID_STATUSES = {
    "ACTIVE", "PROBATION", "NOTICE_PERIOD",
    "ON_LEAVE", "SUSPENDED", "RESIGNED", "TERMINATED",
}


INITIAL_VALID_STATUSES = {"ACTIVE", "PROBATION"}


class EmployeeCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=255)
    official_email: EmailStr | None = Field(None)
    personal_email: EmailStr | None = Field(None)
    email: EmailStr = Field(...)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    phone: str | None = Field(None, max_length=20)
    mobile_number: str | None = Field(None, max_length=20)
    alternate_phone: str | None = Field(None, max_length=20)
    gender: str | None = Field(None, max_length=10)
    date_of_birth: str | None = None
    profile_photo_url: str | None = None
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    role_ids: list[str] = []
    reporting_manager_id: uuid.UUID | None = None
    date_of_joining: str | None = None
    employment_type: str | None = Field(None, max_length=20)
    account_status: str = "ACTIVE"
    emergency_contact_name: str | None = Field(None, max_length=200)
    emergency_contact_phone: str | None = Field(None, max_length=20)
    address: str | None = None
    is_department_head: bool = False
    team_id: uuid.UUID | None = None
    is_team_lead: bool = False

    @classmethod
    def validate_status(cls, v: str) -> str:
        if v.upper() not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {v}. Must be one of {VALID_STATUSES}")
        return v.upper()


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=255)
    official_email: EmailStr | None = Field(None)
    personal_email: EmailStr | None = Field(None)
    email: EmailStr | None = Field(None)
    username: str | None = Field(None, min_length=3, max_length=100)
    password: str | None = Field(None, min_length=8)
    phone: str | None = Field(None, max_length=20)
    mobile_number: str | None = Field(None, max_length=20)
    alternate_phone: str | None = Field(None, max_length=20)
    gender: str | None = Field(None, max_length=10)
    date_of_birth: str | None = None
    profile_photo_url: str | None = None
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    role_ids: list[str] | None = None
    reporting_manager_id: uuid.UUID | None = None
    date_of_joining: str | None = None
    employment_type: str | None = Field(None, max_length=20)
    account_status: str | None = None
    emergency_contact_name: str | None = Field(None, max_length=200)
    emergency_contact_phone: str | None = Field(None, max_length=20)
    address: str | None = None
    is_department_head: bool | None = None
    team_id: uuid.UUID | None = None
    is_team_lead: bool | None = None


class EmployeeResponse(BaseModel):
    id: uuid.UUID
    employee_code: str
    first_name: str
    middle_name: str | None = None
    last_name: str
    display_name: str | None = None
    official_email: str | None = None
    personal_email: str | None = None
    email: str
    username: str
    phone: str | None = None
    mobile_number: str | None = None
    alternate_phone: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    profile_photo_url: str | None = None
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    date_of_joining: date | None = None
    employment_type: str | None = None
    account_status: str
    is_active: bool
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    address: str | None = None
    created_at: datetime
    updated_at: datetime
    is_department_head: bool = False
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    role_in_team: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EmployeeListResponse(EmployeeResponse):
    role_ids: list[str] = []
    role_names: list[str] = []
    department_name: str | None = None
    designation_name: str | None = None
    reporting_manager_name: str | None = None


class EmployeeOffboardBlocker(BaseModel):
    type: str
    count: int
    items: list[dict] = []


class EmployeeOffboardCheck(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    current_status: str
    can_offboard: bool = False
    blockers: list[EmployeeOffboardBlocker] = []


class TransferReportsRequest(BaseModel):
    new_manager_id: uuid.UUID
    employee_ids: list[uuid.UUID]


class TransferTeamRequest(BaseModel):
    new_lead_id: uuid.UUID
    team_ids: list[uuid.UUID]


class TransferDepartmentRequest(BaseModel):
    new_head_id: uuid.UUID
    department_ids: list[uuid.UUID]


class EmployeeRoleHistoryResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    old_role_id: uuid.UUID | None = None
    old_role_name: str | None = None
    new_role_id: uuid.UUID
    new_role_name: str | None = None
    effective_from: date
    effective_to: date | None = None
    reason: str
    changed_by: uuid.UUID | None = None
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeReportingHistoryResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    old_manager_id: uuid.UUID | None = None
    old_manager_name: str | None = None
    new_manager_id: uuid.UUID | None = None
    new_manager_name: str | None = None
    reason: str | None = None
    changed_by: uuid.UUID | None = None
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)
