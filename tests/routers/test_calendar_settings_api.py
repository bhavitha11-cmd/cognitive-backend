import pytest
from unittest.mock import MagicMock, patch
from fastapi import status
from app.database.session import get_db
from app.models.calendar_settings import CalendarSettings
from tests.conftest import TEST_EMPLOYEE_ID


@pytest.fixture
def clean_db_override(test_app):
    override = test_app.dependency_overrides.get(get_db)
    yield override
    if override:
        test_app.dependency_overrides[get_db] = override


@pytest.fixture(autouse=True)
def mock_auth_engine():
    with patch("app.services.auth_engine_service.AuthorizationEngine.has_permission", return_value=True):
        yield


def create_full_calendar_settings(**kwargs) -> CalendarSettings:
    defaults = {
        "id": TEST_EMPLOYEE_ID,
        "working_days": "MON,TUE,WED,THU,FRI,SAT",
        "weekend_days": "SUN",
        "weekly_off_rules": None,
        "office_start_time": "09:00",
        "office_end_time": "18:00",
        "default_daily_hours": 8.0,
        "working_hours_per_day": 8.0,
        "enable_birthdays": True,
        "enable_company_events": True,
        "enable_holidays": True,
        "enable_task_events": True,
        "enable_project_events": True,
        "color_holiday": "#EF4444",
        "color_birthday": "#EC4899",
        "color_task": "#3B82F6",
        "color_project": "#10B981",
        "color_company_event": "#8B5CF6"
    }
    defaults.update(kwargs)
    return CalendarSettings(**defaults)


@pytest.mark.asyncio
async def test_get_calendar_settings(async_client, test_app, clean_db_override):
    mock_settings = create_full_calendar_settings(weekly_off_rules={"SAT": [2, 4]})

    mock_db = MagicMock()
    mock_db.scalar.return_value = mock_settings
    test_app.dependency_overrides[get_db] = lambda: mock_db

    resp = await async_client.get("/api/v1/calendar/settings")
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["weekly_off_rules"] == {"SAT": [2, 4]}


@pytest.mark.asyncio
async def test_put_calendar_settings_valid(async_client, test_app, clean_db_override):
    mock_settings = create_full_calendar_settings()
    mock_db = MagicMock()
    mock_db.scalar.return_value = mock_settings
    test_app.dependency_overrides[get_db] = lambda: mock_db

    payload = {
        "weekly_off_rules": {"SAT": [2, 4], "WED": [1, 3]}
    }
    resp = await async_client.put("/api/v1/calendar/settings", json=payload)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["weekly_off_rules"] == {"SAT": [2, 4], "WED": [1, 3]}
    assert mock_settings.weekly_off_rules == {"SAT": [2, 4], "WED": [1, 3]}


@pytest.mark.asyncio
async def test_put_calendar_settings_normalization(async_client, test_app, clean_db_override):
    mock_settings = create_full_calendar_settings()
    mock_db = MagicMock()
    mock_db.scalar.return_value = mock_settings
    test_app.dependency_overrides[get_db] = lambda: mock_db

    payload = {
        "weekly_off_rules": {"SAT": [4, 2, 4, 2]}
    }
    resp = await async_client.put("/api/v1/calendar/settings", json=payload)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["weekly_off_rules"] == {"SAT": [2, 4]}


@pytest.mark.asyncio
async def test_put_calendar_settings_validation_errors(async_client, test_app, clean_db_override):
    mock_settings = create_full_calendar_settings()
    mock_db = MagicMock()
    mock_db.scalar.return_value = mock_settings
    test_app.dependency_overrides[get_db] = lambda: mock_db

    resp = await async_client.put("/api/v1/calendar/settings", json={"weekly_off_rules": {"FOO": [2]}})
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    resp = await async_client.put("/api/v1/calendar/settings", json={"weekly_off_rules": {"SAT": [6]}})
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_put_calendar_settings_auto_cleanup(async_client, test_app, clean_db_override):
    mock_settings = create_full_calendar_settings(weekly_off_rules={"SAT": [2, 4]})
    mock_db = MagicMock()
    mock_db.scalar.return_value = mock_settings
    test_app.dependency_overrides[get_db] = lambda: mock_db

    payload = {
        "weekend_days": "SUN,SAT",
        "weekly_off_rules": {"SAT": [2, 4]}
    }
    resp = await async_client.put("/api/v1/calendar/settings", json=payload)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["weekly_off_rules"] is None
    assert mock_settings.weekly_off_rules is None
