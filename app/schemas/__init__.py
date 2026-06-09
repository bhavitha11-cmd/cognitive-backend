from app.schemas.common import APIResponse
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from app.schemas.designation import DesignationCreate, DesignationUpdate, DesignationResponse
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
    EmployeeOffboardCheck,
    EmployeeOffboardBlocker,
    TransferReportsRequest,
    TransferTeamRequest,
    TransferDepartmentRequest,
    EmployeeRoleHistoryResponse,
    EmployeeReportingHistoryResponse,
)
from app.schemas.employee_role import EmployeeRoleCreate, EmployeeRoleResponse
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse
from app.schemas.team_member import TeamMemberCreate, TeamMemberUpdate, TeamMemberResponse

__all__ = [
    "APIResponse",
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentResponse",
    "DesignationCreate",
    "DesignationUpdate",
    "DesignationResponse",
    "EmployeeCreate",
    "EmployeeUpdate",
    "EmployeeResponse",
    "EmployeeListResponse",
    "EmployeeOffboardCheck",
    "EmployeeOffboardBlocker",
    "TransferReportsRequest",
    "TransferTeamRequest",
    "TransferDepartmentRequest",
    "EmployeeRoleHistoryResponse",
    "EmployeeReportingHistoryResponse",
    "EmployeeRoleCreate",
    "EmployeeRoleResponse",
    "TeamCreate",
    "TeamUpdate",
    "TeamResponse",
    "TeamMemberCreate",
    "TeamMemberUpdate",
    "TeamMemberResponse",
]
