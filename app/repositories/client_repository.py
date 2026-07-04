from uuid import UUID

from sqlalchemy import func, or_, select

from app.models.client import Client
from app.repositories.base import BaseRepository


class ClientRepository(BaseRepository):
    def get_by_id(self, id: UUID) -> Client | None:
        return self.db.get(Client, id)

    def get_by_name(self, name: str) -> Client | None:
        return self.db.scalars(
            select(Client).where(Client.name.ilike(name))
        ).first()

    def get_by_code(self, code: str) -> Client | None:
        return self.db.scalars(
            select(Client).where(Client.client_code.ilike(code))
        ).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[Client]:
        stmt = select(Client)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Client.name.ilike(pattern),
                    Client.client_code.ilike(pattern),
                    Client.industry.ilike(pattern),
                    Client.contact_person.ilike(pattern),
                    Client.country.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(Client.is_active == is_active)
        stmt = stmt.order_by(Client.name).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).all())

    def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        stmt = select(func.count(Client.id))
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Client.name.ilike(pattern),
                    Client.client_code.ilike(pattern),
                    Client.industry.ilike(pattern),
                    Client.contact_person.ilike(pattern),
                    Client.country.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(Client.is_active == is_active)
        return self.db.scalar(stmt) or 0

    def create(self, data: dict) -> Client:
        client = Client(**data)
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)
        return client

    def update(self, client: Client, data: dict) -> Client:
        for key, value in data.items():
            setattr(client, key, value)
        self.db.commit()
        self.db.refresh(client)
        return client

    def delete(self, client: Client) -> None:
        self.db.delete(client)
        self.db.commit()

    def get_lookup(self, limit: int = 100) -> list:
        stmt = (
            select(Client.id, Client.name, Client.client_code)
            .where(Client.is_active == True)
            .order_by(Client.name)
            .limit(limit)
        )
        return list(self.db.execute(stmt).all())
