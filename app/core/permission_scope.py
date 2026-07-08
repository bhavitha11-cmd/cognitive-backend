"""
Centralized PermissionScope enum — single source of truth for all
scope values used across the entire Cognitive ERP authorization platform.

Every service, router, and frontend must reference these values.
"""

from enum import Enum


class PermissionScope(str, Enum):
    """Data access scope for a specific action on a feature."""

    NONE = "NONE"
    OWNED = "OWNED"
    ADDED = "ADDED"
    ADDED_OWNED = "ADDED_OWNED"
    TEAM = "TEAM"
    DEPARTMENT = "DEPARTMENT"
    COMPANY = "COMPANY"
    ALL = "ALL"

    @classmethod
    def choices(cls) -> list[str]:
        """Return all scope values as a list of strings (for UI dropdowns)."""
        return [s.value for s in cls]

    @classmethod
    def has_access(cls, scope: str) -> bool:
        """Return True if the scope grants any level of access (i.e. is not NONE)."""
        return scope != cls.NONE.value


# Standard CRUD actions
class PermissionAction(str, Enum):
    VIEW = "view"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
