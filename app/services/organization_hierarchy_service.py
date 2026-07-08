from uuid import UUID
from sqlalchemy.orm import Session

from app.core.hierarchy_cache import HierarchyCache
from app.repositories.hierarchy_repository import HierarchyRepository
from app.schemas.hierarchy import HierarchyNode
from app.models.employee import Employee

class OrganizationHierarchyService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = HierarchyRepository(db)
        self.cache = HierarchyCache.get_instance()
        self._ensure_cache()
    
    def _ensure_cache(self) -> None:
        """Rebuild cache if stale or empty."""
        if self.cache.is_stale():
            relationships = self.repo.get_all_reporting_relationships()
            self.cache.build(relationships)

    def get_visible_employee_ids(self, employee_id: UUID) -> set[UUID]:
        """Returns the set of employee IDs whose data this employee is allowed to see.
        This includes the employee themselves, and all their descendants in the reporting tree."""
        visible = self.cache.get_descendant_ids(employee_id)
        visible.add(employee_id)
        return visible

    def is_manager_of(self, manager_id: UUID, employee_id: UUID) -> bool:
        """True if manager_id is an ancestor of employee_id in the reporting hierarchy."""
        return self.cache.is_ancestor_of(manager_id, employee_id)

    def can_see_employee(self, requester_id: UUID, target_id: UUID) -> bool:
        """True if requester_id can see target_id's metrics/records."""
        if requester_id == target_id:
            return True
        return self.is_manager_of(requester_id, target_id)

    def get_manager_chain(self, employee_id: UUID) -> list[HierarchyNode]:
        """Ordered list of managers above the employee, from immediate to root."""
        ancestor_ids = self.cache.get_ancestor_ids(employee_id)
        if not ancestor_ids:
            return []
            
        employees = self.repo.get_employee_details(set(ancestor_ids))
        emp_map = {e.id: e for e in employees}
        
        chain = []
        for depth, ans_id in enumerate(ancestor_ids, start=1):
            emp = emp_map.get(ans_id)
            if emp:
                chain.append(
                    HierarchyNode(
                        id=emp.id,
                        employee_code=emp.employee_code,
                        display_name=f"{emp.first_name} {emp.last_name}",
                        designation=emp.designation.name if emp.designation else None,
                        department=emp.department.name if emp.department else None,
                        depth=depth
                    )
                )
        return chain

    def get_direct_report_ids(self, employee_id: UUID) -> set[UUID]:
        """IDs of immediate reports."""
        return self.cache.get_children(employee_id)

    def get_subordinates(self, employee_id: UUID) -> list[HierarchyNode]:
        """Direct report details."""
        child_ids = self.cache.get_children(employee_id)
        if not child_ids:
            return []
            
        employees = self.repo.get_employee_details(child_ids)
        return [
            HierarchyNode(
                id=emp.id,
                employee_code=emp.employee_code,
                display_name=f"{emp.first_name} {emp.last_name}",
                designation=emp.designation.name if emp.designation else None,
                department=emp.department.name if emp.department else None,
                depth=1
            )
            for emp in employees
        ]

    def get_organization_tree(self, root_id: UUID | None = None) -> list[dict]:
        """Returns the full recursive tree structure or a subtree rooted at root_id."""
        if root_id:
            sub_ids = self.cache.get_descendant_ids(root_id)
            sub_ids.add(root_id)
        else:
            sub_ids = self.cache._all_ids
            
        if not sub_ids:
            return []

        employees = self.repo.get_employee_details(sub_ids)
        emp_map = {e.id: e for e in employees}
        
        children_map = {}
        roots = []
        
        if root_id:
            if root_id in emp_map:
                roots.append(emp_map[root_id])
        else:
            for e in employees:
                mgr_id = self.cache.get_parent(e.id)
                if mgr_id and mgr_id in emp_map:
                    pass
                else:
                    roots.append(e)

        for e in employees:
            mgr_id = self.cache.get_parent(e.id)
            if mgr_id and mgr_id in emp_map:
                children_map.setdefault(mgr_id, []).append(e)

        def build_node(emp: Employee) -> dict:
            return {
                "id": str(emp.id),
                "label": f"{emp.first_name} {emp.last_name}",
                "designation": emp.designation.name if emp.designation else None,
                "department": emp.department.name if emp.department else None,
                "status": emp.account_status,
                "avatar": emp.profile_photo_url,
                "children": [build_node(child) for child in children_map.get(emp.id, [])],
            }

        return [build_node(r) for r in roots]

    def validate_reporting_change(self, employee_id: UUID, new_manager_id: UUID) -> None:
        """Validates that a reporting manager assignment won't create circular hierarchy."""
        if self.repo.detect_cycle_cte(employee_id, new_manager_id):
            raise ValueError("Circular reporting hierarchy detected")

    def get_common_manager(self, emp_a: UUID, emp_b: UUID) -> HierarchyNode | None:
        """Finds the lowest common manager (LCA) in the reporting chain."""
        if emp_a == emp_b:
            parent_id = self.cache.get_parent(emp_a)
            if not parent_id:
                return None
            return self._enrich_single_node(parent_id, depth=1)

        chain_a = self.cache.get_ancestor_ids(emp_a)
        chain_b = self.cache.get_ancestor_ids(emp_b)
        
        set_b = set(chain_b)
        for idx, ans_id in enumerate(chain_a, start=1):
            if ans_id in set_b:
                return self._enrich_single_node(ans_id, depth=idx)
        return None

    def get_hierarchy_depth(self, employee_id: UUID) -> int:
        """Returns depth of the employee in the org tree (0 = root)."""
        return len(self.cache.get_ancestor_ids(employee_id))

    def _enrich_single_node(self, employee_id: UUID, depth: int) -> HierarchyNode | None:
        employees = self.repo.get_employee_details({employee_id})
        if not employees:
            return None
        emp = employees[0]
        return HierarchyNode(
            id=emp.id,
            employee_code=emp.employee_code,
            display_name=f"{emp.first_name} {emp.last_name}",
            designation=emp.designation.name if emp.designation else None,
            department=emp.department.name if emp.department else None,
            depth=depth
        )

    def invalidate_cache(self) -> None:
        """Invalidates the hierarchy cache."""
        self.cache.invalidate()
