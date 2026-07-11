import re
import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator


# ── enums ─────────────────────────────────────────────────────────────────────

class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


class EmploymentType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERN = "INTERN"


VALID_STATUSES = {
    "ACTIVE", "PROBATION", "NOTICE_PERIOD",
    "ON_LEAVE", "SUSPENDED", "RESIGNED", "TERMINATED",
}
INITIAL_VALID_STATUSES = {"ACTIVE", "PROBATION"}


def _validate_phone(v: str | None) -> str | None:
    if v is None:
        return v
    clean = re.sub(r"[\s\-]", "", v)
    if not re.match(r"^\+?[\d]{7,15}$", clean):
        raise ValueError("Invalid phone number format")
    return v


# ── request schemas ───────────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=255)
    official_email: EmailStr | None = None
    personal_email: EmailStr | None = None
    email: EmailStr = Field(...)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    phone: str | None = Field(None, max_length=20)
    mobile_number: str | None = Field(None, max_length=20)
    alternate_phone: str | None = Field(None, max_length=20)
    gender: Gender | None = None
    date_of_birth: date | None = None
    profile_photo_url: str | None = Field(None, max_length=500)
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] = Field(default=[], max_length=20)
    reporting_manager_id: uuid.UUID | None = None
    date_of_joining: date | None = None
    employment_type: EmploymentType | None = None
    account_status: str = Field(default="ACTIVE")
    emergency_contact_name: str | None = Field(None, max_length=200)
    emergency_contact_phone: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=1000)
    is_department_head: bool = False
    team_id: uuid.UUID | None = None
    is_team_lead: bool = False

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        import re
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator("account_status")
    @classmethod
    def validate_account_status(cls, v: str) -> str:
        upper = v.upper()
        if upper not in INITIAL_VALID_STATUSES:
            raise ValueError(f"New employee status must be one of {INITIAL_VALID_STATUSES}")
        return upper

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: date | None) -> date | None:
        if v and v >= date.today():
            raise ValueError("Date of birth must be in the past")
        return v

    @field_validator("phone", "mobile_number", "alternate_phone", mode="before")
    @classmethod
    def validate_phones(cls, v):
        return _validate_phone(v)

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def validate_emergency_phone(cls, v):
        if v is None or v == "":
            return v
        import re
        clean = re.sub(r"[\s\-]", "", v)
        if not re.match(r"^\d{10}$", clean):
            raise ValueError("Emergency contact phone must be exactly 10 digits")
        return clean


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=255)
    official_email: EmailStr | None = None
    personal_email: EmailStr | None = None
    email: EmailStr | None = None
    username: str | None = Field(None, min_length=3, max_length=100)
    password: str | None = Field(None, min_length=8, max_length=128)
    phone: str | None = Field(None, max_length=20)
    mobile_number: str | None = Field(None, max_length=20)
    alternate_phone: str | None = Field(None, max_length=20)
    gender: Gender | None = None
    date_of_birth: date | None = None
    profile_photo_url: str | None = Field(None, max_length=500)
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] | None = None
    reporting_manager_id: uuid.UUID | None = None
    date_of_joining: date | None = None
    employment_type: EmploymentType | None = None
    account_status: str | None = None
    emergency_contact_name: str | None = Field(None, max_length=200)
    emergency_contact_phone: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=1000)
    is_department_head: bool | None = None
    team_id: uuid.UUID | None = None
    is_team_lead: bool | None = None

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in v):
            raise ValueError('Password must contain at least one special character')
        return v

    @field_validator("account_status")
    @classmethod
    def validate_account_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        upper = v.upper()
        if upper not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Must be one of {VALID_STATUSES}")
        return upper

    @field_validator("phone", "mobile_number", "alternate_phone", mode="before")
    @classmethod
    def validate_phones(cls, v):
        return _validate_phone(v)

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def validate_emergency_phone(cls, v):
        if v is None or v == "":
            return v
        import re
        clean = re.sub(r"[\s\-]", "", v)
        if not re.match(r"^\d{10}$", clean):
            raise ValueError("Emergency contact phone must be exactly 10 digits")
        return clean


# ── response schemas ──────────────────────────────────────────────────────────

class EmployeeLookupItem(BaseModel):
    id: uuid.UUID
    display_name: str
    employee_code: str
    department_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] = []
    team_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


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
    is_team_lead: bool = False


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
    new_role_id: uuid.UUID | None = None
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
