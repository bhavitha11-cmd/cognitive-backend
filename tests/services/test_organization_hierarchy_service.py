import pytest
from unittest.mock import MagicMock
from uuid import uuid4, UUID
from app.services.organization_hierarchy_service import OrganizationHierarchyService
from app.core.hierarchy_cache import HierarchyCache
from app.models.employee import Employee
from app.models.designation import Designation
from app.models.department import Department

@pytest.fixture(autouse=True)
def clean_cache():
    cache = HierarchyCache.get_instance()
    cache.invalidate()
    yield
    cache.invalidate()

def make_mock_emp_details(emp_id, first_name, last_name, code, des_name=None, dept_name=None):
    emp = MagicMock(spec=Employee)
    emp.id = emp_id
    emp.first_name = first_name
    emp.last_name = last_name
    emp.employee_code = code
    emp.profile_photo_url = f"https://example.com/avatar/{code}.png"
    emp.account_status = "ACTIVE"
    
    if des_name:
        des = MagicMock(spec=Designation)
        des.name = des_name
        emp.designation = des
    else:
        emp.designation = None
        
    if dept_name:
        dept = MagicMock(spec=Department)
        dept.name = dept_name
        emp.department = dept
    else:
        emp.department = None
        
    return emp

def test_service_ensure_cache_and_visible_ids(mock_db):
    ceo_id = uuid4()
    mgr_id = uuid4()
    emp_id = uuid4()
    
    relationships = [(ceo_id, None), (mgr_id, ceo_id), (emp_id, mgr_id)]
    
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    service.repo.get_all_reporting_relationships.return_value = relationships
    service.invalidate_cache()
    service._ensure_cache()
    
    # Verify relationships are loaded
    assert service.cache.get_parent(mgr_id) == ceo_id
    assert service.cache.get_parent(emp_id) == mgr_id
    
    # Test visible employee IDs
    assert service.get_visible_employee_ids(ceo_id) == {ceo_id, mgr_id, emp_id}
    assert service.get_visible_employee_ids(mgr_id) == {mgr_id, emp_id}
    assert service.get_visible_employee_ids(emp_id) == {emp_id}

def test_is_manager_of_and_can_see(mock_db):
    ceo_id = uuid4()
    mgr_id = uuid4()
    emp_id = uuid4()
    
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    service.repo.get_all_reporting_relationships.return_value = [
        (ceo_id, None),
        (mgr_id, ceo_id),
        (emp_id, mgr_id)
    ]
    service.invalidate_cache()
    service._ensure_cache()
    
    assert service.is_manager_of(ceo_id, emp_id) is True
    assert service.is_manager_of(mgr_id, emp_id) is True
    assert service.is_manager_of(emp_id, ceo_id) is False
    
    assert service.can_see_employee(ceo_id, emp_id) is True
    assert service.can_see_employee(emp_id, emp_id) is True
    assert service.can_see_employee(emp_id, ceo_id) is False

def test_get_manager_chain(mock_db):
    ceo_id = uuid4()
    mgr_id = uuid4()
    emp_id = uuid4()
    
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    service.repo.get_all_reporting_relationships.return_value = [
        (ceo_id, None),
        (mgr_id, ceo_id),
        (emp_id, mgr_id)
    ]
    
    ceo_emp = make_mock_emp_details(ceo_id, "CEO", "User", "EMP001", "CEO", "Exec")
    mgr_emp = make_mock_emp_details(mgr_id, "Manager", "User", "EMP002", "Manager", "Eng")
    
    service.repo.get_employee_details.return_value = [ceo_emp, mgr_emp]
    service.invalidate_cache()
    service._ensure_cache()
    
    chain = service.get_manager_chain(emp_id)
    assert len(chain) == 2
    assert chain[0].id == mgr_id
    assert chain[0].depth == 1
    assert chain[0].display_name == "Manager User"
    assert chain[0].designation == "Manager"
    assert chain[0].department == "Eng"
    
    assert chain[1].id == ceo_id
    assert chain[1].depth == 2
    assert chain[1].display_name == "CEO User"
    assert chain[1].designation == "CEO"
    assert chain[1].department == "Exec"

def test_get_subordinates(mock_db):
    ceo_id = uuid4()
    mgr_id = uuid4()
    emp_id = uuid4()
    
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    service.repo.get_all_reporting_relationships.return_value = [
        (ceo_id, None),
        (mgr_id, ceo_id),
        (emp_id, mgr_id)
    ]
    
    mgr_emp = make_mock_emp_details(mgr_id, "Manager", "User", "EMP002", "Manager", "Eng")
    service.repo.get_employee_details.return_value = [mgr_emp]
    service.invalidate_cache()
    service._ensure_cache()
    
    subs = service.get_subordinates(ceo_id)
    assert len(subs) == 1
    assert subs[0].id == mgr_id
    assert subs[0].display_name == "Manager User"
    assert subs[0].depth == 1

def test_get_organization_tree(mock_db):
    ceo_id = uuid4()
    mgr_id = uuid4()
    emp_id = uuid4()
    
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    service.repo.get_all_reporting_relationships.return_value = [
        (ceo_id, None),
        (mgr_id, ceo_id),
        (emp_id, mgr_id)
    ]
    
    ceo_emp = make_mock_emp_details(ceo_id, "CEO", "User", "EMP001", "CEO", "Exec")
    mgr_emp = make_mock_emp_details(mgr_id, "Manager", "User", "EMP002", "Manager", "Eng")
    emp_emp = make_mock_emp_details(emp_id, "Employee", "User", "EMP003", "Engineer", "Eng")
    
    service.repo.get_employee_details.return_value = [ceo_emp, mgr_emp, emp_emp]
    service.invalidate_cache()
    service._ensure_cache()
    
    tree = service.get_organization_tree()
    assert len(tree) == 1
    assert tree[0]["id"] == str(ceo_id)
    assert tree[0]["label"] == "CEO User"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["id"] == str(mgr_id)
    assert len(tree[0]["children"][0]["children"]) == 1
    assert tree[0]["children"][0]["children"][0]["id"] == str(emp_id)

def test_validate_reporting_change(mock_db):
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    
    # No cycle
    service.repo.detect_cycle_cte.return_value = False
    service.validate_reporting_change(uuid4(), uuid4()) # should not raise
    
    # Cycle
    service.repo.detect_cycle_cte.return_value = True
    with pytest.raises(ValueError, match="Circular reporting hierarchy detected"):
        service.validate_reporting_change(uuid4(), uuid4())

def test_get_common_manager(mock_db):
    ceo_id = uuid4()
    mgr1_id = uuid4()
    mgr2_id = uuid4()
    emp1_id = uuid4()
    emp2_id = uuid4()
    
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    service.repo.get_all_reporting_relationships.return_value = [
        (ceo_id, None),
        (mgr1_id, ceo_id),
        (mgr2_id, ceo_id),
        (emp1_id, mgr1_id),
        (emp2_id, mgr2_id)
    ]
    
    ceo_emp = make_mock_emp_details(ceo_id, "CEO", "User", "EMP001", "CEO", "Exec")
    mgr1_emp = make_mock_emp_details(mgr1_id, "Manager1", "User", "EMP002", "Manager", "Eng")
    
    service.repo.get_employee_details.side_effect = lambda ids: (
        [ceo_emp] if ceo_id in ids else [mgr1_emp] if mgr1_id in ids else []
    )
    service.invalidate_cache()
    service._ensure_cache()
    
    # emp1 and emp2 share CEO as lowest common manager
    lca = service.get_common_manager(emp1_id, emp2_id)
    assert lca is not None
    assert lca.id == ceo_id
    
    # emp1 and mgr1 share CEO as lowest common manager (since mgr1's manager is CEO)
    lca2 = service.get_common_manager(emp1_id, mgr1_id)
    assert lca2 is not None
    assert lca2.id == ceo_id

def test_get_hierarchy_depth(mock_db):
    ceo_id = uuid4()
    mgr_id = uuid4()
    emp_id = uuid4()
    
    service = OrganizationHierarchyService(mock_db)
    service.repo = MagicMock()
    service.repo.get_all_reporting_relationships.return_value = [
        (ceo_id, None),
        (mgr_id, ceo_id),
        (emp_id, mgr_id)
    ]
    service.invalidate_cache()
    service._ensure_cache()
    
    assert service.get_hierarchy_depth(ceo_id) == 0
    assert service.get_hierarchy_depth(mgr_id) == 1
    assert service.get_hierarchy_depth(emp_id) == 2
