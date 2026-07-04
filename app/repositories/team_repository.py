from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.models.team import Team
from app.models.team_member import TeamMember
from app.repositories.base import BaseRepository


class TeamRepository(BaseRepository):
    def get_all(self, department_id: UUID | None = None) -> list[Team]:
        stmt = select(Team).options(
            joinedload(Team.department),
            selectinload(Team.members).selectinload(TeamMember.employee),
        )
        if department_id:
            stmt = stmt.where(Team.department_id == department_id)
        return list(
            self.db.scalars(
                stmt.order_by(Team.team_name)
            ).unique().all()
        )

    def get_by_id(self, id: UUID) -> Team | None:
        return self.db.scalars(
            select(Team)
            .options(
                joinedload(Team.department),
                selectinload(Team.members).selectinload(TeamMember.employee),
            )
            .where(Team.id == id)
        ).unique().first()

    def get_by_name(self, name: str) -> Team | None:
        return self.db.scalars(
            select(Team).where(Team.team_name == name)
        ).first()

    def get_by_code(self, code: str) -> Team | None:
        return self.db.scalars(
            select(Team).where(Team.team_code == code)
        ).first()

    def create(self, data: dict) -> Team:
        team = Team(**data)
        self.db.add(team)
        self.db.commit()
        self.db.refresh(team)
        return team

    def update(self, team: Team, data: dict) -> Team:
        for key, value in data.items():
            setattr(team, key, value)
        self.db.commit()
        self.db.refresh(team)
        return team

    def delete(self, team: Team) -> None:
        self.db.delete(team)
        self.db.commit()

    def get_lookup(self, limit: int = 100) -> list:
        stmt = (
            select(Team.id, Team.team_name, Team.team_code, Team.department_id)
            .where(Team.is_active == True)
            .order_by(Team.team_name)
            .limit(limit)
        )
        return list(self.db.execute(stmt).all())
