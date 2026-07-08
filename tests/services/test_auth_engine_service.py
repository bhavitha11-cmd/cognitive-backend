from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch
import pytest

from app.core.permission_scope import PermissionScope
from app.services.auth_engine_service import AuthorizationEngine


@pytest.fixture
def db():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None
    mock_db.scalars.return_value = MagicMock()
    mock_db.scalars.return_value.all.return_value = []
    mock_db.scalars.return_value.first.return_value = None
    return mock_db


@pytest.fixture
def engine(db):
    return AuthorizationEngine(db)


def test_super_admin_always_authorized(db, engine):
    user_id = uuid.uuid4()
    # Mock _is_super_admin to return True
    with patch.object(engine, "_is_super_admin", return_value=True):
        assert engine.has_permission(user_id, "projects", "view") is True
        assert engine.has_permission(user_id, "tasks", "delete") is True
        
        # Access filter should return sa_true()
        sa_filter = engine.build_access_filter(user_id, "projects", "view")
        assert sa_filter is True or getattr(sa_filter, "clause", None) is None  # standard true value or sa_true
        
        # can_access_record should always return True
        assert engine.can_access_record(user_id, "projects", "view") is True


def test_has_permission_scopes(db, engine):
    user_id = uuid.uuid4()
    
    with patch.object(engine, "_is_super_admin", return_value=False):
        # 1. NONE scope
        with patch.object(engine, "_resolve_scope", return_value=PermissionScope.NONE.value):
            assert engine.has_permission(user_id, "projects", "view") is False
            
        # 2. OWNED scope
        with patch.object(engine, "_resolve_scope", return_value=PermissionScope.OWNED.value):
            assert engine.has_permission(user_id, "projects", "view") is True

        # 3. TEAM scope
        with patch.object(engine, "_resolve_scope", return_value=PermissionScope.TEAM.value):
            assert engine.has_permission(user_id, "projects", "view") is True

        # 4. ALL scope
        with patch.object(engine, "_resolve_scope", return_value=PermissionScope.ALL.value):
            assert engine.has_permission(user_id, "projects", "view") is True


def test_can_access_record_owned_scope(db, engine):
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    
    with patch.object(engine, "_is_super_admin", return_value=False):
        with patch.object(engine, "_resolve_scope", return_value=PermissionScope.OWNED.value):
            # Access allowed when user owns the record
            assert engine.can_access_record(user_id, "projects", "view", record_owner_id=user_id) is True
            # Access denied when user does not own the record
            assert engine.can_access_record(user_id, "projects", "view", record_owner_id=other_user_id) is False


def test_can_access_record_team_scope(db, engine):
    user_id = uuid.uuid4()
    team_member_id = uuid.uuid4()
    other_id = uuid.uuid4()
    
    with patch.object(engine, "_is_super_admin", return_value=False), \
         patch.object(engine, "_resolve_scope", return_value=PermissionScope.TEAM.value), \
         patch.object(engine, "_get_team_ids", return_value={user_id, team_member_id}):
        
        # Access allowed if target owner is in team
        assert engine.can_access_record(user_id, "projects", "view", record_owner_id=team_member_id) is True
        # Access denied if target owner is not in team
        assert engine.can_access_record(user_id, "projects", "view", record_owner_id=other_id) is False


def test_can_access_record_department_scope(db, engine):
    user_id = uuid.uuid4()
    dept_id = uuid.uuid4()
    other_dept_id = uuid.uuid4()
    
    with patch.object(engine, "_is_super_admin", return_value=False), \
         patch.object(engine, "_resolve_scope", return_value=PermissionScope.DEPARTMENT.value), \
         patch.object(engine, "_get_user_department_id", return_value=dept_id), \
         patch.object(engine, "_get_department_member_ids", return_value={user_id}):
        
        # Access allowed if department matches
        assert engine.can_access_record(user_id, "projects", "view", record_department_id=dept_id) is True
        # Access denied if department doesn't match
        assert engine.can_access_record(user_id, "projects", "view", record_department_id=other_dept_id) is False
