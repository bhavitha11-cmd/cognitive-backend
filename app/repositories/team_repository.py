from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.team import Team
from app.repositories.base import BaseRepository


class TeamRepository(BaseRepository):
    def get_all(self) -> list[Team]:
        return list(
            self.db.scalars(
                select(Team)
                .options(joinedload(Team.department), joinedload(Team.members))
                .order_by(Team.team_name)
            ).unique().all()
        )

    def get_by_id(self, id: UUID) -> Team | None:
        return self.db.scalars(
            select(Team)
            .options(joinedload(Team.department), joinedload(Team.members))
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
