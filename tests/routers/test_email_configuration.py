import pytest
from unittest.mock import patch, MagicMock
import uuid
from datetime import datetime, timezone

from app.database.session import get_db
from app.services.auth_engine_service import AuthorizationEngine
from app.models.email_configuration import EmailConfiguration
from app.services.email_service import EmailService


@pytest.fixture(autouse=True)
def mock_permissions():
    """Automatically mock all permission checks to return True."""
    with patch.object(AuthorizationEngine, "has_permission", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_db_session(test_app):
    """Override get_db to return a dedicated mock DB session for isolation."""
    db = MagicMock()
    db.scalar.return_value = None
    db.scalars.return_value = MagicMock()
    db.scalars.return_value.unique.return_value = MagicMock()
    db.scalars.return_value.unique.return_value.all.return_value = []
    db.scalars.return_value.all = db.scalars.return_value.unique.return_value.all
    db.scalars.return_value.first.return_value = None
    db.get.return_value = None
    
    # Override
    test_app.dependency_overrides[get_db] = lambda: db
    yield db
    # Cleanup after test
    if get_db in test_app.dependency_overrides:
        del test_app.dependency_overrides[get_db]


@pytest.mark.asyncio
async def test_list_email_configurations(async_client, mock_db_session):
    # Setup mock data
    config1 = EmailConfiguration(
        id=uuid.uuid4(),
        name="M365 Mailbox",
        provider="microsoft_graph",
        sender_email="info@company.com",
        is_active=True,
        connection_status="connected",
        tenant_id="tenant-123",
        client_id="client-123",
        client_secret="encrypted-secret",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_db_session.scalars.return_value.all.return_value = [config1]

    resp = await async_client.get("/api/v1/settings/email-configurations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["data"]["configurations"]) == 1
    assert body["data"]["configurations"][0]["name"] == "M365 Mailbox"
    assert body["data"]["configurations"][0]["provider"] == "microsoft_graph"
    # Ensure sensitive secret is masked as boolean in the output
    assert "client_secret" not in body["data"]["configurations"][0]
    assert body["data"]["configurations"][0]["graph_has_secret"] is True


@pytest.mark.asyncio
async def test_create_email_configuration(async_client, mock_db_session):
    payload = {
        "name": "SMTP Mailbox",
        "provider": "smtp",
        "sender_email": "smtp@company.com",
        "is_active": False,
        "smtp_host": "smtp.company.com",
        "smtp_port": 587,
        "smtp_username": "smtp_user",
        "smtp_password": "my_smtp_password",
        "smtp_use_tls": True
    }

    resp = await async_client.post("/api/v1/settings/email-configurations", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["name"] == "SMTP Mailbox"
    assert body["data"]["provider"] == "smtp"
    assert body["data"]["smtp_has_password"] is True
    assert mock_db_session.add.called
    assert mock_db_session.commit.called


@pytest.mark.asyncio
async def test_update_email_configuration(async_client, mock_db_session):
    config_id = uuid.uuid4()
    existing_config = EmailConfiguration(
        id=config_id,
        name="Old Name",
        provider="microsoft_graph",
        sender_email="old@company.com",
        is_active=False,
        connection_status="untested",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_db_session.scalar.return_value = existing_config

    payload = {
        "name": "New Name",
        "sender_email": "new@company.com",
        "is_active": True
    }

    resp = await async_client.put(f"/api/v1/settings/email-configurations/{config_id}", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["name"] == "New Name"
    assert body["data"]["sender_email"] == "new@company.com"
    assert body["data"]["is_active"] is True
    assert mock_db_session.commit.called


@pytest.mark.asyncio
async def test_delete_active_email_configuration_fails(async_client, mock_db_session):
    config_id = uuid.uuid4()
    active_config = EmailConfiguration(
        id=config_id,
        name="Active Config",
        provider="microsoft_graph",
        sender_email="active@company.com",
        is_active=True,
    )
    mock_db_session.scalar.return_value = active_config

    resp = await async_client.delete(f"/api/v1/settings/email-configurations/{config_id}")
    assert resp.status_code == 400
    body = resp.json()
    assert "cannot delete" in body["detail"].lower()


@pytest.mark.asyncio
async def test_delete_inactive_email_configuration_succeeds(async_client, mock_db_session):
    config_id = uuid.uuid4()
    inactive_config = EmailConfiguration(
        id=config_id,
        name="Inactive Config",
        provider="microsoft_graph",
        sender_email="inactive@company.com",
        is_active=False,
    )
    mock_db_session.scalar.return_value = inactive_config

    resp = await async_client.delete(f"/api/v1/settings/email-configurations/{config_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert mock_db_session.delete.called
    assert mock_db_session.commit.called


@pytest.mark.asyncio
async def test_activate_email_configuration(async_client, mock_db_session):
    config_id = uuid.uuid4()
    config = EmailConfiguration(
        id=config_id,
        name="Target Config",
        provider="microsoft_graph",
        sender_email="test@company.com",
        is_active=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_db_session.scalar.return_value = config

    resp = await async_client.post(f"/api/v1/settings/email-configurations/{config_id}/activate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["is_active"] is True
    assert mock_db_session.commit.called


@pytest.mark.asyncio
async def test_test_unsaved_connection_endpoint(async_client):
    payload = {
        "name": "Test Form",
        "provider": "smtp",
        "sender_email": "test@company.com",
        "smtp_host": "smtp.company.com",
        "smtp_port": 587,
        "smtp_username": "user",
        "smtp_password": "pass",
        "smtp_use_tls": True,
        "test_recipient": "recipient@company.com"
    }

    with patch.object(EmailService, "test_connection") as mock_test:
        mock_test.return_value = (True, None)

        resp = await async_client.post("/api/v1/settings/email-configurations/test", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["success"] is True
        assert body["data"]["recipient"] == "recipient@company.com"


@pytest.mark.asyncio
async def test_test_saved_connection_endpoint(async_client, mock_db_session):
    config_id = uuid.uuid4()
    config = EmailConfiguration(
        id=config_id,
        name="Saved Config",
        provider="microsoft_graph",
        sender_email="saved@company.com",
        is_active=False,
    )
    def mock_scalar(query):
        q_str = str(query).lower()
        if "email_configuration" in q_str:
            return config
        elif "employee" in q_str:
            mock_emp = MagicMock()
            mock_emp.email = "admin@company.com"
            return mock_emp
        return None
    mock_db_session.scalar.side_effect = mock_scalar

    with patch.object(EmailService, "test_connection") as mock_test:
        mock_test.return_value = (True, None)

        resp = await async_client.post(f"/api/v1/settings/email-configurations/{config_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["success"] is True
        assert mock_test.called
