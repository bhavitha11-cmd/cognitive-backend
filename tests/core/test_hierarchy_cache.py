import time
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from app.core.hierarchy_cache import HierarchyCache

def test_cache_singleton():
    cache1 = HierarchyCache.get_instance()
    cache2 = HierarchyCache.get_instance()
    assert cache1 is cache2

def test_cache_build_and_traversal():
    cache = HierarchyCache.get_instance()
    cache.invalidate()
    
    # Create test UUIDs
    ceo = uuid4()
    mgr = uuid4()
    emp1 = uuid4()
    emp2 = uuid4()
    unrelated = uuid4()
    
    # Adjacency relationships:
    # CEO -> Manager -> Emp1, Emp2
    relationships = [
        (ceo, None),
        (mgr, ceo),
        (emp1, mgr),
        (emp2, mgr),
        (unrelated, None)
    ]
    
    cache.build(relationships)
    
    # 1. Parents check
    assert cache.get_parent(ceo) is None
    assert cache.get_parent(mgr) == ceo
    assert cache.get_parent(emp1) == mgr
    assert cache.get_parent(emp2) == mgr
    
    # 2. Children check
    assert cache.get_children(ceo) == {mgr}
    assert cache.get_children(mgr) == {emp1, emp2}
    assert cache.get_children(emp1) == set()
    
    # 3. Ancestors check
    assert cache.get_ancestor_ids(emp1) == [mgr, ceo]
    assert cache.get_ancestor_ids(ceo) == []
    
    # 4. Descendants check
    assert cache.get_descendant_ids(ceo) == {mgr, emp1, emp2}
    assert cache.get_descendant_ids(mgr) == {emp1, emp2}
    assert cache.get_descendant_ids(emp1) == set()
    
    # 5. Is ancestor of
    assert cache.is_ancestor_of(ceo, mgr) is True
    assert cache.is_ancestor_of(ceo, emp1) is True
    assert cache.is_ancestor_of(mgr, emp1) is True
    assert cache.is_ancestor_of(emp1, ceo) is False
    assert cache.is_ancestor_of(ceo, unrelated) is False
    
    # 6. Roots check
    assert cache.get_roots() == {ceo, unrelated}

def test_cache_stale_and_invalidation():
    cache = HierarchyCache.get_instance()
    cache.invalidate()
    assert cache.is_stale() is True
    
    cache.build([])
    assert cache.is_stale() is False
    
    cache.invalidate()
    assert cache.is_stale() is True

def test_cache_ttl():
    cache = HierarchyCache.get_instance()
    cache.invalidate()
    
    cache.build([])
    assert cache.is_stale() is False
    
    # Artificially set built_at to 6 minutes ago
    cache._built_at = datetime.now(timezone.utc) - timedelta(seconds=301)
    assert cache.is_stale() is True

def test_cycle_traversal_protection():
    # If bad data with cycle A -> B -> A is loaded
    cache = HierarchyCache.get_instance()
    cache.invalidate()
    
    a = uuid4()
    b = uuid4()
    
    relationships = [
        (a, b),
        (b, a)
    ]
    cache.build(relationships)
    
    # Should not infinite loop
    ancestors_a = cache.get_ancestor_ids(a)
    assert len(ancestors_a) <= 2
    
    descendants_a = cache.get_descendant_ids(a)
    assert len(descendants_a) <= 2
