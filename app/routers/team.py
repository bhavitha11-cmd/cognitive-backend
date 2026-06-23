import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse
from app.schemas.team_member import TeamMemberCreate, TeamMemberUpdate
from app.services.team_service import TeamService
from app.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/teams",
    tags=["Teams"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user)) -> TeamService:
    from uuid import UUID
    try:
        uid = UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return TeamService(db, current_user_id=uid)


@router.get("", response_model=APIResponse)
def list_teams(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: TeamService = Depends(_get_service),
):
    teams = service.get_all()
    total = len(teams)
    paginated = teams[skip: skip + limit]
    return APIResponse(
        success=True,
        message="Teams retrieved successfully",
        data={"teams": [t.model_dump() for t in paginated], "total": total, "skip": skip, "limit": limit},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("HR", "create"))])
def create_team(data: TeamCreate, service: TeamService = Depends(_get_service)):
    try:
        team = service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Team created successfully",
        data={"team": TeamResponse.model_validate(team).model_dump()},
    )


@router.get("/{id}", response_model=APIResponse)
def get_team(id: uuid.UUID, service: TeamService = Depends(_get_service)):
    team = service.get_by_id(id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return APIResponse(
        success=True,
        message="Team retrieved successfully",
        data={"team": team.model_dump(), "members": [m.model_dump() for m in service.get_team_members(id)]},
    )


@router.put("/{id}", response_model=APIResponse,
            dependencies=[Depends(require_permission("HR", "edit"))])
def update_team(id: uuid.UUID, data: TeamUpdate, service: TeamService = Depends(_get_service)):
    try:
        team = service.update(id, data)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Team updated successfully",
        data={"team": TeamResponse.model_validate(team).model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse,
               dependencies=[Depends(require_permission("HR", "delete"))])
def deactivate_team(id: uuid.UUID, service: TeamService = Depends(_get_service)):
    try:
        service.deactivate(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Team deactivated successfully")


# ── Team Members ───────────────────────────────────────────────────────────────

@router.post("/{team_id}/members", response_model=APIResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("HR", "edit"))])
def add_team_member(team_id: uuid.UUID, data: TeamMemberCreate, service: TeamService = Depends(_get_service)):
    try:
        member = service.add_member(team_id, data)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Member added to team",
        data={"member": member.model_dump()},
    )


@router.put("/{team_id}/members/{member_id}", response_model=APIResponse,
            dependencies=[Depends(require_permission("HR", "edit"))])
def update_team_member(
    team_id: uuid.UUID,
    member_id: uuid.UUID,
    data: TeamMemberUpdate,
    service: TeamService = Depends(_get_service),
):
    try:
        member = service.update_member(team_id, member_id, data)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Team member updated",
        data={"member": member.model_dump()},
    )


@router.delete("/{team_id}/members/{member_id}", response_model=APIResponse,
               dependencies=[Depends(require_permission("HR", "edit"))])
def remove_team_member(
    team_id: uuid.UUID,
    member_id: uuid.UUID,
    service: TeamService = Depends(_get_service),
):
    try:
        service.remove_member(team_id, member_id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Member removed from team")
