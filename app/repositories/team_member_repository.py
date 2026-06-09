from uuid import UUID

from sqlalchemy import select, and_

from app.models.team_member import TeamMember
from app.repositories.base import BaseRepository


class TeamMemberRepository(BaseRepository):
    def get_by_id(self, id: UUID) -> TeamMember | None:
        return self.db.get(TeamMember, id)

    def get_by_team_and_employee(self, team_id: UUID, employee_id: UUID) -> TeamMember | None:
        return self.db.scalars(
            select(TeamMember).where(
                and_(
                    TeamMember.team_id == team_id,
                    TeamMember.employee_id == employee_id,
                )
            )
        ).first()

    def get_by_employee(self, employee_id: UUID) -> list[TeamMember]:
        return list(
            self.db.scalars(
                select(TeamMember).where(TeamMember.employee_id == employee_id)
            ).all()
        )

    def get_primary_team(self, employee_id: UUID) -> TeamMember | None:
        return self.db.scalars(
            select(TeamMember).where(
                and_(
                    TeamMember.employee_id == employee_id,
                    TeamMember.is_primary_team == True,
                )
            )
        ).first()

    def get_active_members(self, team_id: UUID) -> list[TeamMember]:
        return list(
            self.db.scalars(
                select(TeamMember)
                .where(
                    and_(
                        TeamMember.team_id == team_id,
                        TeamMember.left_at.is_(None),
                    )
                )
            ).all()
        )

    def create(self, data: dict) -> TeamMember:
        member = TeamMember(**data)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def update(self, member: TeamMember, data: dict) -> TeamMember:
        for key, value in data.items():
            setattr(member, key, value)
        self.db.commit()
        self.db.refresh(member)
        return member

    def delete(self, member: TeamMember) -> None:
        self.db.delete(member)
        self.db.commit()
