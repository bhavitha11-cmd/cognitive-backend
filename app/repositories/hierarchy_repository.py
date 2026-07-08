from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload
from app.repositories.base import BaseRepository
from app.models.employee import Employee

class HierarchyRepository(BaseRepository):
    """SQL queries for organizational hierarchy data."""

    def get_all_reporting_relationships(self) -> list[tuple[UUID, UUID | None]]:
        """Single flat query returning (employee_id, reporting_manager_id)
        for all active employees. This feeds the cache."""
        stmt = select(Employee.id, Employee.reporting_manager_id).where(
            Employee.is_active == True
        )
        result = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in result]

    def detect_cycle_cte(self, employee_id: UUID, proposed_manager_id: UUID) -> bool:
        """PostgreSQL recursive CTE to check if assigning proposed_manager_id
        as the manager of employee_id would create a cycle.
        Returns True if cycle detected."""
        if employee_id == proposed_manager_id:
            return True

        result = self.db.execute(
            text("""
                WITH RECURSIVE reporting_chain AS (
                    SELECT id, reporting_manager_id FROM employees WHERE id = :start_id
                    UNION ALL
                    SELECT e.id, e.reporting_manager_id
                    FROM employees e
                    INNER JOIN reporting_chain rc ON e.id = rc.reporting_manager_id
                    WHERE rc.reporting_manager_id IS NOT NULL
                )
                SELECT id FROM reporting_chain WHERE id = :check_id
            """),
            {"start_id": str(proposed_manager_id), "check_id": str(employee_id)}
        )
        return result.fetchone() is not None

    def get_employee_details(self, employee_ids: set[UUID]) -> list[Employee]:
        """Fetch name, designation, department for a set of employee IDs.
        Used to enrich hierarchy nodes AFTER cache-based ID resolution."""
        if not employee_ids:
            return []
        stmt = (
            select(Employee)
            .options(
                joinedload(Employee.designation),
                joinedload(Employee.department)
            )
            .where(Employee.id.in_(employee_ids))
        )
        return list(self.db.scalars(stmt).unique().all())
