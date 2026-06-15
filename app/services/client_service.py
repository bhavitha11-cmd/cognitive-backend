from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.client import Client
from app.repositories.client_repository import ClientRepository
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.services.audit_service import AuditService


class ClientService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.repo = ClientRepository(db)
        self.current_user_id = current_user_id

    def _to_response(self, client: Client) -> ClientResponse:
        project_count = len(client.projects) if client.projects is not None else 0
        response = ClientResponse.model_validate(client)
        response.project_count = project_count
        return response

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[ClientResponse], int]:
        clients = self.repo.get_all(skip=skip, limit=limit, search=search, is_active=is_active)
        total = self.repo.count(search=search, is_active=is_active)
        return [self._to_response(c) for c in clients], total

    def get_by_id(self, id: UUID) -> ClientResponse:
        client = self.repo.get_by_id(id)
        if not client:
            raise ValueError(f"Client with id {id} not found")
        return self._to_response(client)

    def _auto_generate_code(self) -> str:
        total = self.repo.count()
        return f"CLT-{total + 1:04d}"

    def create(self, data: ClientCreate) -> ClientResponse:
        client_code = data.client_code.strip() if data.client_code else ""
        if not client_code:
            client_code = self._auto_generate_code()

        # Check name uniqueness (case insensitive)
        if self.repo.get_by_name(data.name):
            raise ValueError(f"Client with name '{data.name}' already exists")

        # Check code uniqueness
        if self.repo.get_by_code(client_code):
            raise ValueError(f"Client with code '{client_code}' already exists")

        payload = data.model_dump()
        payload["client_code"] = client_code
        if self.current_user_id:
            payload["created_by"] = self.current_user_id

        try:
            client = self.repo.create(payload)
            AuditService.log(
                self.repo.db,
                "client",
                client.id,
                "CREATE",
                performed_by=self.current_user_id,
                new_value={"name": client.name, "client_code": client.client_code},
            )
            return self._to_response(client)
        except Exception:
            self.repo.db.rollback()
            raise

    def update(self, id: UUID, data: ClientUpdate) -> ClientResponse:
        client = self.repo.get_by_id(id)
        if not client:
            raise ValueError(f"Client with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"].lower() != client.name.lower():
            existing = self.repo.get_by_name(update_data["name"])
            if existing and existing.id != id:
                raise ValueError(f"Client with name '{update_data['name']}' already exists")

        if "client_code" in update_data and update_data["client_code"].lower() != client.client_code.lower():
            existing = self.repo.get_by_code(update_data["client_code"])
            if existing and existing.id != id:
                raise ValueError(f"Client with code '{update_data['client_code']}' already exists")

        old_values = {k: getattr(client, k, None) for k in update_data}
        try:
            client = self.repo.update(client, update_data)
            AuditService.log(
                self.repo.db,
                "client",
                id,
                "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values,
                new_value=update_data,
            )
            return self._to_response(client)
        except Exception:
            self.repo.db.rollback()
            raise

    def delete(self, id: UUID) -> None:
        client = self.repo.get_by_id(id)
        if not client:
            raise ValueError(f"Client with id {id} not found")

        # Check no active projects linked to this client
        active_project_count = 0
        if client.projects:
            active_project_count = sum(
                1 for p in client.projects if getattr(p, "is_active", True)
            )
        if active_project_count:
            raise ValueError(
                f"Cannot delete client '{client.name}': {active_project_count} active project(s) are linked. "
                f"Reassign or close them first."
            )

        try:
            AuditService.log(
                self.repo.db,
                "client",
                id,
                "DELETE",
                performed_by=self.current_user_id,
                old_value={"name": client.name, "client_code": client.client_code},
            )
            # Soft delete
            self.repo.update(client, {"is_active": False})
        except Exception:
            self.repo.db.rollback()
            raise
