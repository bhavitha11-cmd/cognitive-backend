from pydantic import BaseModel
from uuid import UUID

class HierarchyNode(BaseModel):
    """Single node in the reporting hierarchy."""
    id: UUID
    employee_code: str
    display_name: str | None = None
    designation: str | None = None
    department: str | None = None
    depth: int

class ManagerChainResponse(BaseModel):
    """Response model for manager chain queries."""
    employee_id: UUID
    chain: list[HierarchyNode]
    chain_length: int

class SubordinatesResponse(BaseModel):
    """Response model for direct subordinates queries."""
    employee_id: UUID
    subordinates: list[HierarchyNode]
    count: int
