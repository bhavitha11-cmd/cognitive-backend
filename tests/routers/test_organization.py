import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from app.schemas.hierarchy import HierarchyNode
from app.services.organization_hierarchy_service import OrganizationHierarchyService
from app.core.rbac import require_data_access, UserContext, DataAccessLevel
from tests.conftest import TEST_EMPLOYEE_ID

@pytest.mark.asyncio
async def test_get_manager_chain_api(async_client):
    target_id = uuid4()
    mock_node = HierarchyNode(
        id=uuid4(),
        employee_code="EMP001",
        display_name="CEO User",
        designation="CEO",
        department="Exec",
        depth=1
    )
    
    with patch.object(OrganizationHierarchyService, "get_manager_chain") as mock_svc:
        mock_svc.return_value = [mock_node]
        
        resp = await async_client.get(f"/api/v1/organization/{target_id}/manager-chain")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["chain"]) == 1
        assert body["data"]["chain"][0]["employee_code"] == "EMP001"
        assert body["data"]["chain_length"] == 1

@pytest.mark.asyncio
async def test_get_subordinates_api_self(async_client):
    mock_sub = HierarchyNode(
        id=uuid4(),
        employee_code="EMP002",
        display_name="Subordinate User",
        designation="Engineer",
        department="Eng",
        depth=1
    )
    
    with patch.object(OrganizationHierarchyService, "get_subordinates") as mock_svc:
        mock_svc.return_value = [mock_sub]
        
        resp = await async_client.get(f"/api/v1/organization/{TEST_EMPLOYEE_ID}/subordinates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["subordinates"]) == 1
        assert body["data"]["subordinates"][0]["employee_code"] == "EMP002"

@pytest.mark.asyncio
async def test_get_subordinates_api_other_authorized(async_client, test_app):
    other_id = uuid4()
    mock_sub = HierarchyNode(
        id=uuid4(),
        employee_code="EMP002",
        display_name="Subordinate User",
        designation="Engineer",
        department="Eng",
        depth=1
    )
    
    def override_data_access():
        return UserContext(
            employee_id=TEST_EMPLOYEE_ID,
            role_codes=["ENGINEER"],
            role_names=["Engineer"],
            is_super_admin=False,
            data_access_level=DataAccessLevel.SELF
        )
    
    test_app.dependency_overrides[require_data_access] = override_data_access
    
    try:
        with patch.object(OrganizationHierarchyService, "is_manager_of") as mock_mgr_check, \
             patch.object(OrganizationHierarchyService, "get_subordinates") as mock_svc:
             
            mock_mgr_check.return_value = True
            mock_svc.return_value = [mock_sub]
            
            resp = await async_client.get(f"/api/v1/organization/{other_id}/subordinates")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert len(body["data"]["subordinates"]) == 1
    finally:
        del test_app.dependency_overrides[require_data_access]

@pytest.mark.asyncio
async def test_get_subordinates_api_other_unauthorized(async_client, test_app):
    other_id = uuid4()
    
    def override_data_access():
        return UserContext(
            employee_id=TEST_EMPLOYEE_ID,
            role_codes=["ENGINEER"],
            role_names=["Engineer"],
            is_super_admin=False,
            data_access_level=DataAccessLevel.SELF
        )
        
    test_app.dependency_overrides[require_data_access] = override_data_access
    
    try:
        with patch.object(OrganizationHierarchyService, "is_manager_of") as mock_mgr_check:
            mock_mgr_check.return_value = False
            
            resp = await async_client.get(f"/api/v1/organization/{other_id}/subordinates")
            assert resp.status_code == 403
            body = resp.json()
            assert "permission" in body["detail"].lower()
    finally:
        del test_app.dependency_overrides[require_data_access]
