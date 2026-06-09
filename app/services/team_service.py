import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.employee import Employee
from app.repositories.team_repository import TeamRepository
from app.repositories.team_member_repository import TeamMemberRepository
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse
from app.schemas.team_member import TeamMemberCreate, TeamMemberUpdate, TeamMemberResponse


class TeamService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TeamRepository(db)
        self.member_repo = TeamMemberRepository(db)

    # ---- Team CRUD ----

    def get_all(self) -> list[TeamResponse]:
        teams = self.repo.get_all()
        result = []
        for t in teams:
            active_members = [m for m in t.members if m.left_at is None]
            lead = next((m for m in active_members if m.role_in_team == "LEAD"), None)
            lead_name = f"{lead.employee.first_name} {lead.employee.last_name}" if lead and lead.employee else None
            lead_id = lead.employee_id if lead else None
            result.append(TeamResponse(
                id=t.id,
                team_name=t.team_name,
                team_code=t.team_code,
                description=t.description,
                department_id=t.department_id,
                department_name=t.department.name if t.department else None,
                member_count=len(active_members),
                is_active=t.is_active,
                created_at=t.created_at,
                updated_at=t.updated_at,
                team_lead_name=lead_name,
                team_lead_id=lead_id,
            ))
        return result

    def get_by_id(self, id: uuid.UUID) -> TeamResponse | None:
        team = self.repo.get_by_id(id)
        if not team:
            return None
        active_members = [m for m in team.members if m.left_at is None]
        lead = next((m for m in active_members if m.role_in_team == "LEAD"), None)
        lead_name = f"{lead.employee.first_name} {lead.employee.last_name}" if lead and lead.employee else None
        lead_id = lead.employee_id if lead else None
        return TeamResponse(
            id=team.id,
            team_name=team.team_name,
            team_code=team.team_code,
            description=team.description,
            department_id=team.department_id,
            department_name=team.department.name if team.department else None,
            member_count=len(active_members),
            is_active=team.is_active,
            created_at=team.created_at,
            updated_at=team.updated_at,
            team_lead_name=lead_name,
            team_lead_id=lead_id,
        )

    def create(self, data: TeamCreate) -> Team:
        if self.repo.get_by_name(data.team_name):
            raise ValueError(f"Team with name '{data.team_name}' already exists")
        if self.repo.get_by_code(data.team_code):
            raise ValueError(f"Team with code '{data.team_code}' already exists")
        return self.repo.create(data.model_dump())

    def update(self, id: uuid.UUID, data: TeamUpdate) -> Team:
        team = self.repo.get_by_id(id)
        if not team:
            raise ValueError(f"Team with id {id} not found")
        update_data = data.model_dump(exclude_unset=True)
        if "team_name" in update_data and update_data["team_name"] != team.team_name:
            existing = self.repo.get_by_name(update_data["team_name"])
            if existing and existing.id != id:
                raise ValueError(f"Team with name '{update_data['team_name']}' already exists")
        if "team_code" in update_data and update_data["team_code"] != team.team_code:
            existing = self.repo.get_by_code(update_data["team_code"])
            if existing and existing.id != id:
                raise ValueError(f"Team with code '{update_data['team_code']}' already exists")
        return self.repo.update(team, update_data)

    def deactivate(self, id: uuid.UUID) -> Team:
        team = self.repo.get_by_id(id)
        if not team:
            raise ValueError(f"Team with id {id} not found")
        return self.repo.update(team, {"is_active": False})

    # ---- Team Members ----

    def add_member(self, team_id: uuid.UUID, data: TeamMemberCreate) -> TeamMemberResponse:
        team = self.repo.get_by_id(team_id)
        if not team:
            raise ValueError(f"Team with id {team_id} not found")
        employee = self.db.get(Employee, data.employee_id)
        if not employee:
            raise ValueError(f"Employee with id {data.employee_id} not found")
        if not employee.is_active:
            raise ValueError("Cannot add inactive employee to team")
        existing = self.member_repo.get_by_team_and_employee(team_id, data.employee_id)
        if existing and existing.left_at is None:
            raise ValueError("Employee is already an active member of this team")
        if existing and existing.left_at is not None:
            # Rejoin: reset left_at
            return self._update_member_response(
                self.member_repo.update(existing, {
                    "left_at": None,
                    "role_in_team": data.role_in_team,
                    "is_primary_team": data.is_primary_team,
                    "joined_at": datetime.utcnow(),
                })
            )
        # Enforce single primary team
        if data.is_primary_team:
            current_primary = self.member_repo.get_primary_team(data.employee_id)
            if current_primary and current_primary.team_id != team_id:
                self.member_repo.update(current_primary, {"is_primary_team": False})
        member = self.member_repo.create({
            "team_id": team_id,
            "employee_id": data.employee_id,
            "role_in_team": data.role_in_team,
            "is_primary_team": data.is_primary_team,
        })
        return self._build_member_response(member)

    def update_member(self, member_id: uuid.UUID, data: TeamMemberUpdate) -> TeamMemberResponse:
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise ValueError(f"Team member entry with id {member_id} not found")
        update_data = data.model_dump(exclude_unset=True)
        if "is_primary_team" in update_data and update_data["is_primary_team"]:
            current_primary = self.member_repo.get_primary_team(member.employee_id)
            if current_primary and current_primary.id != member_id:
                self.member_repo.update(current_primary, {"is_primary_team": False})
        return self._build_member_response(
            self.member_repo.update(member, update_data)
        )

    def remove_member(self, member_id: uuid.UUID) -> None:
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise ValueError(f"Team member entry with id {member_id} not found")
        self.member_repo.update(member, {
            "left_at": datetime.utcnow(),
            "is_primary_team": False
        })

    def get_team_members(self, team_id: uuid.UUID) -> list[TeamMemberResponse]:
        members = self.member_repo.get_active_members(team_id)
        return [self._build_member_response(m) for m in members]

    # ---- Helpers ----

    def _build_member_response(self, member) -> TeamMemberResponse:
        emp_name = None
        emp_code = None
        if member.employee:
            emp_name = f"{member.employee.first_name} {member.employee.last_name}"
            emp_code = member.employee.employee_code
        return TeamMemberResponse(
            id=member.id,
            team_id=member.team_id,
            employee_id=member.employee_id,
            employee_name=emp_name,
            employee_code=emp_code,
            role_in_team=member.role_in_team,
            is_primary_team=member.is_primary_team,
            joined_at=member.joined_at,
            left_at=member.left_at,
        )

    def _update_member_response(self, member) -> TeamMemberResponse:
        return self._build_member_response(member)
