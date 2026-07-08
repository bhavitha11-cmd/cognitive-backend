import threading
from datetime import datetime, timezone
from uuid import UUID

class HierarchyCache:
    """Module-level singleton that caches the reporting relationship graph."""
    
    _instance: "HierarchyCache | None" = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._parent_map: dict[UUID, UUID | None] = {}   # child -> parent
        self._children_map: dict[UUID, set[UUID]] = {}    # parent -> {children}
        self._all_ids: set[UUID] = set()
        self._built_at: datetime | None = None
        self._ttl_seconds: int = 300  # 5 minutes
    
    @classmethod
    def get_instance(cls) -> "HierarchyCache":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def build(self, relationships: list[tuple[UUID, UUID | None]]) -> None:
        """Build the adjacency maps from a flat list of (id, manager_id) tuples."""
        parent_map = {}
        children_map = {}
        all_ids = set()
        for emp_id, mgr_id in relationships:
            parent_map[emp_id] = mgr_id
            all_ids.add(emp_id)
            if mgr_id is not None:
                children_map.setdefault(mgr_id, set()).add(emp_id)
        with self._lock:
            self._parent_map = parent_map
            self._children_map = children_map
            self._all_ids = all_ids
            self._built_at = datetime.now(timezone.utc)
            
    def invalidate(self) -> None:
        """Force rebuild on next access."""
        with self._lock:
            self._built_at = None
            
    def is_stale(self) -> bool:
        """True if cache was never built or TTL has expired."""
        if self._built_at is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self._built_at).total_seconds()
        return elapsed >= self._ttl_seconds
        
    def get_parent(self, employee_id: UUID) -> UUID | None:
        """Immediate manager."""
        return self._parent_map.get(employee_id)
        
    def get_children(self, employee_id: UUID) -> set[UUID]:
        """Direct report IDs."""
        return self._children_map.get(employee_id, set())
        
    def get_ancestor_ids(self, employee_id: UUID) -> list[UUID]:
        """Walk UP: [immediate_manager, ..., root]. Ordered by depth."""
        ancestors = []
        curr = self.get_parent(employee_id)
        visited = {employee_id} # prevent infinite loops
        while curr is not None and curr not in visited:
            ancestors.append(curr)
            visited.add(curr)
            curr = self.get_parent(curr)
        return ancestors
        
    def get_descendant_ids(self, employee_id: UUID) -> set[UUID]:
        """Walk DOWN: all employees below. Unordered."""
        descendants = set()
        queue = list(self.get_children(employee_id))
        visited = {employee_id}
        while queue:
            curr = queue.pop(0)
            if curr not in visited:
                visited.add(curr)
                descendants.add(curr)
                queue.extend(self.get_children(curr))
        return descendants
        
    def is_ancestor_of(self, ancestor_id: UUID, descendant_id: UUID) -> bool:
        """True if ancestor_id is anywhere above descendant_id in the chain."""
        if ancestor_id == descendant_id:
            return False
        curr = self.get_parent(descendant_id)
        visited = {descendant_id}
        while curr is not None and curr not in visited:
            if curr == ancestor_id:
                return True
            visited.add(curr)
            curr = self.get_parent(curr)
        return False
        
    def get_roots(self) -> set[UUID]:
        """Employees with no manager (tree roots)."""
        return {emp_id for emp_id, mgr_id in self._parent_map.items() if mgr_id is None}
