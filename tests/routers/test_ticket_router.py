from __future__ import annotations
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest

from app.services.ticket_service import TicketService
from app.repositories.ticket_repository import TicketRepository
from app.models.ticket_category import TicketCategory
from app.models.ticket_priority import TicketPriority
from app.models.ticket_status import TicketStatus
from app.models.ticket import Ticket

@pytest.mark.asyncio
@patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True)
async def test_get_categories(mock_has_perm, async_client):
    with patch.object(TicketRepository, "get_all_categories") as mock_get_cats:
        mock_cat = TicketCategory(
            id=uuid.uuid4(),
            name="Hardware",
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        mock_get_cats.return_value = [mock_cat]

        resp = await async_client.get("/api/v1/tickets/settings/categories")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["categories"]) == 1
        assert body["data"]["categories"][0]["name"] == "Hardware"

@pytest.mark.asyncio
@patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True)
async def test_create_category(mock_has_perm, async_client):
    with patch.object(TicketRepository, "get_category_by_name") as mock_find, \
         patch.object(TicketRepository, "create_category") as mock_create:
        
        mock_find.return_value = None
        mock_cat = TicketCategory(
            id=uuid.uuid4(),
            name="Network",
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        mock_create.return_value = mock_cat

        resp = await async_client.post("/api/v1/tickets/settings/categories", json={"name": "Network", "is_active": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["category"]["name"] == "Network"

@pytest.mark.asyncio
@patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True)
async def test_get_my_tickets(mock_has_perm, async_client):
    with patch.object(TicketService, "get_my_tickets") as mock_my_tickets:
        t = MagicMock()
        t.id = uuid.uuid4()
        t.ticket_number = "TCK-101"
        t.category_id = uuid.uuid4()
        t.category.name = "IT"
        t.ticket_type_id = uuid.uuid4()
        t.ticket_type.name = "Laptop Issue"
        t.subject = "Keyboard broke"
        t.status_id = uuid.uuid4()
        t.status.name = "Open"
        t.priority_id = uuid.uuid4()
        t.priority.name = "Medium"
        t.created_at = datetime.now()
        t.updated_at = datetime.now()

        mock_my_tickets.return_value = [t]

        resp = await async_client.get("/api/v1/tickets/my")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["tickets"]) == 1
        assert body["data"]["tickets"][0]["ticket_number"] == "TCK-101"

@pytest.mark.asyncio
@patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True)
async def test_raise_ticket(mock_has_perm, async_client):
    with patch.object(TicketService, "raise_ticket") as mock_raise:
        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        mock_ticket.ticket_number = "TCK-102"
        mock_raise.return_value = mock_ticket

        payload = {
            "category_id": str(uuid.uuid4()),
            "ticket_type_id": str(uuid.uuid4()),
            "subject": "VPN not working",
            "description": "Fails to connect with auth error",
            "priority_id": str(uuid.uuid4()),
            "attachments": []
        }

        resp = await async_client.post("/api/v1/tickets/my", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["ticket"]["ticket_number"] == "TCK-102"

@pytest.mark.asyncio
@patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True)
@patch("app.services.auth_engine_service.AuthorizationEngine._is_super_admin", return_value=False)
async def test_get_category_tickets(mock_is_super, mock_has_perm, async_client):
    with patch.object(TicketService, "get_category_tickets") as mock_get_cat_tickets:
        t = MagicMock()
        t.id = uuid.uuid4()
        t.ticket_number = "TCK-103"
        t.category_id = uuid.uuid4()
        t.category.name = "Stationery"
        t.ticket_type_id = uuid.uuid4()
        t.ticket_type.name = "Notebook"
        t.subject = "Need notebook"
        t.status_id = uuid.uuid4()
        t.status.name = "Open"
        t.priority_id = uuid.uuid4()
        t.priority.name = "Low"
        t.raised_by_id = uuid.uuid4()
        t.created_at = datetime.now()
        t.updated_at = datetime.now()

        mock_get_cat_tickets.return_value = [t]

        resp = await async_client.get("/api/v1/tickets/category")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["tickets"]) == 1
        assert body["data"]["tickets"][0]["ticket_number"] == "TCK-103"

@pytest.mark.asyncio
@patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True)
@patch("app.services.auth_engine_service.AuthorizationEngine._is_super_admin", return_value=False)
async def test_update_ticket_status(mock_is_super, mock_has_perm, async_client):
    with patch.object(TicketService, "update_ticket_status") as mock_update:
        mock_update.return_value = MagicMock()
        
        ticket_id = uuid.uuid4()
        status_id = uuid.uuid4()

        resp = await async_client.put(f"/api/v1/tickets/{ticket_id}/status", params={"status_id": str(status_id)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "updated successfully" in body["message"].lower()

@pytest.mark.asyncio
@patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True)
@patch("app.services.auth_engine_service.AuthorizationEngine._is_super_admin", return_value=False)
async def test_add_comment(mock_is_super, mock_has_perm, async_client):
    with patch.object(TicketService, "add_comment") as mock_comment:
        c = MagicMock()
        c.id = uuid.uuid4()
        c.comment = "Working on it"
        c.commented_by_id = uuid.uuid4()
        c.created_at = datetime.now()
        mock_comment.return_value = c

        ticket_id = uuid.uuid4()
        resp = await async_client.post(f"/api/v1/tickets/{ticket_id}/comments", json={"comment": "Working on it"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["comment"]["comment"] == "Working on it"
