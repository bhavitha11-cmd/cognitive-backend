from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch
import pytest

from app.core.seeder import seed_modules_and_features, migrate_boolean_permissions
from app.models.module import Module
from app.models.feature import Feature
from app.models.role_permission import RolePermission


@pytest.fixture
def db():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None
    mock_db.scalars.return_value = MagicMock()
    mock_db.scalars.return_value.all.return_value = []
    mock_db.scalars.return_value.first.return_value = None
    return mock_db


def test_seed_modules_and_features(db):
    # Setup mock to return empty list of existing module keys
    db.scalars.return_value.all.return_value = []

    # Run seeder
    seed_modules_and_features(db)

    # Verify db.add is called (we have at least 10 modules + several features)
    assert db.add.call_count > 0
    assert db.commit.call_count == 1


def test_migrate_boolean_permissions_no_columns(db):
    # If legacy columns aren't found in inspectors, it should skip
    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_inspector = MagicMock()
        mock_inspector.get_columns.return_value = []
        mock_inspect.return_value = mock_inspector

        migrate_boolean_permissions(db)
        # Should not query role_permissions since columns weren't found
        assert db.scalars.call_count == 0
