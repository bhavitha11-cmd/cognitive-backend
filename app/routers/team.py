import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse
from app.schemas.team_member import TeamMemberCreate, TeamMemberUpdate, TeamMemberResponse
from app.services.team_service import TeamService

from app.dependencies import get_current_user

router = APIRouter(
    prefix="/teams",
    tags=["Teams"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(db: Session = Depends(get_db)) -> TeamService:
    return TeamService(db)


@router.get("", response_model=APIResponse)
def list_teams(service: TeamService = Depends(_get_service)):
    teams = service.get_all()
    return APIResponse(
        success=True,
        message="Teams retrieved successfully",
        data={"teams": [t.model_dump() for t in teams]},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
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


@router.put("/{id}", response_model=APIResponse)
def update_team(id: uuid.UUID, data: TeamUpdate, service: TeamService = Depends(_get_service)):
    try:
        team = service.update(id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Team updated successfully",
        data={"team": TeamResponse.model_validate(team).model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse)
def deactivate_team(id: uuid.UUID, service: TeamService = Depends(_get_service)):
    try:
        service.deactivate(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(success=True, message="Team deactivated successfully")


# ---- Team Members ----

@router.post("/{team_id}/members", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def add_team_member(team_id: uuid.UUID, data: TeamMemberCreate, service: TeamService = Depends(_get_service)):
    try:
        member = service.add_member(team_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Member added to team",
        data={"member": member.model_dump()},
    )


@router.put("/{team_id}/members/{member_id}", response_model=APIResponse)
def update_team_member(
    team_id: uuid.UUID, member_id: uuid.UUID,
    data: TeamMemberUpdate, service: TeamService = Depends(_get_service),
):
    try:
        member = service.update_member(member_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Team member updated",
        data={"member": member.model_dump()},
    )


@router.delete("/{team_id}/members/{member_id}", response_model=APIResponse)
def remove_team_member(
    team_id: uuid.UUID, member_id: uuid.UUID,
    service: TeamService = Depends(_get_service),
):
    try:
        service.remove_member(member_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(success=True, message="Member removed from team")
