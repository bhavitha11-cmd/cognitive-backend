import logging
import redis
from sqlalchemy import event
from app.core.config import settings
from app.models.project import Project
from app.models.task import Task
from app.models.time_entry import TimeEntry

logger = logging.getLogger("uvicorn.error")

try:
    # Initialize the Redis connection pool
    redis_client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2.0,  # 2 second connect timeout
        socket_timeout=2.0,          # 2 second socket timeout
    )
except Exception as e:
    logger.error(f"[Redis] Initialization failed: {e}")
    redis_client = None

def get_cache(key: str) -> str | None:
    """Retrieve value from cache. Returns None on cache miss or connection error."""
    if not redis_client:
        return None
    try:
        return redis_client.get(key)
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as ce:
        logger.warning(f"[Redis] Connection error during get: {ce}")
        return None
    except Exception as e:
        logger.error(f"[Redis] Error getting cache for key {key}: {e}")
        return None

def set_cache(key: str, value: str, ttl: int = 30) -> bool:
    """Store value in cache. Returns True on success, False otherwise."""
    if not redis_client:
        return False
    try:
        redis_client.set(key, value, ex=ttl)
        return True
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as ce:
        logger.warning(f"[Redis] Connection error during set: {ce}")
        return False
    except Exception as e:
        logger.error(f"[Redis] Error setting cache for key {key}: {e}")
        return False

def delete_cache(key: str) -> bool:
    """Delete a key from cache. Returns True on success, False otherwise."""
    if not redis_client:
        return False
    try:
        redis_client.delete(key)
        return True
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as ce:
        logger.warning(f"[Redis] Connection error during delete: {ce}")
        return False
    except Exception as e:
        logger.error(f"[Redis] Error deleting cache key {key}: {e}")
        return False

def delete_keys_by_pattern(pattern: str) -> bool:
    """Delete keys matching a wildcard pattern. Returns True on success, False otherwise."""
    if not redis_client:
        return False
    try:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info(f"[Redis] Invalidated {len(keys)} keys with pattern: {pattern}")
        return True
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as ce:
        logger.warning(f"[Redis] Connection error during pattern delete: {ce}")
        return False
    except Exception as e:
        logger.error(f"[Redis] Error deleting cache keys pattern {pattern}: {e}")
        return False

# --- SQLAlchemy Automatic Invalidation Listeners ---

@event.listens_for(Project, 'after_update')
def receive_project_after_update(mapper, connection, target):
    logger.info(f"[Cache Invalidation] Project {target.id} updated. Invalidating keys.")
    delete_cache(f"erp:dashboard:project:{target.id}:summary")
    delete_cache(f"erp:dashboard:project:{target.id}:charts")
    delete_keys_by_pattern("erp:dashboard:executive:*")
    delete_keys_by_pattern("erp:dashboard:performance:rankings*")

@event.listens_for(Task, 'after_insert')
@event.listens_for(Task, 'after_update')
def receive_task_after_write(mapper, connection, target):
    logger.info(f"[Cache Invalidation] Task {target.id} modified. Invalidating keys.")
    delete_cache(f"erp:dashboard:project:{target.project_id}:summary")
    delete_cache(f"erp:dashboard:project:{target.project_id}:charts")
    delete_keys_by_pattern("erp:dashboard:executive:*")
    delete_keys_by_pattern("erp:dashboard:team-leader:*")
    delete_keys_by_pattern("erp:dashboard:employee:*")
    delete_keys_by_pattern("erp:dashboard:performance:rankings*")

@event.listens_for(TimeEntry, 'after_insert')
@event.listens_for(TimeEntry, 'after_update')
def receive_time_entry_after_write(mapper, connection, target):
    logger.info(f"[Cache Invalidation] Time entry {target.id} modified. Invalidating keys.")
    delete_cache(f"erp:dashboard:project:{target.project_id}:summary")
    delete_cache(f"erp:dashboard:project:{target.project_id}:charts")
    delete_keys_by_pattern("erp:dashboard:executive:*")
    delete_keys_by_pattern("erp:dashboard:team-leader:*")
    delete_keys_by_pattern(f"erp:dashboard:employee:{target.employee_id}:*")
    delete_keys_by_pattern("erp:dashboard:performance:rankings*")
