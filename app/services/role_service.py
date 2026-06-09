import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.employee_role import EmployeeRole
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse
from app.services.audit_service import AuditService


def update_child_hierarchies(db: Session, parent_role: Role):
    for child in parent_role.child_roles:
        child.hierarchy_level = parent_role.hierarchy_level + 1
        db.add(child)
        update_child_hierarchies(db, child)


class RoleService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Role]:
        query = select(Role).order_by(Role.hierarchy_level, Role.name)
        return list(self.db.scalars(query).all())

    def get_by_id(self, id: uuid.UUID) -> Role | None:
        return self.db.get(Role, id)

    def create(self, data: RoleCreate) -> Role:
        existing = self.db.scalar(select(Role).where(Role.name == data.name))
        if existing:
            raise ValueError("Role name already exists")

        role_code = data.name.strip().upper().replace(" ", "_")
        existing_code = self.db.scalar(select(Role).where(Role.role_code == role_code))
        if existing_code:
            raise ValueError("A role with a similar name already exists (conflicting role code)")

        hierarchy_level = 1
        if data.parent_role_id:
            parent = self.db.get(Role, data.parent_role_id)
            if not parent:
                raise ValueError("Parent role not found")
            hierarchy_level = parent.hierarchy_level + 1

        db_role = Role(
            name=data.name,
            role_code=role_code,
            description=data.description,
            parent_role_id=data.parent_role_id,
            hierarchy_level=hierarchy_level,
            is_active=data.is_active,
            is_system_role=False,
        )
        self.db.add(db_role)
        self.db.commit()
        self.db.refresh(db_role)

        AuditService.log(self.db, "role", db_role.id, "CREATE",
                         new_value={"name": data.name, "role_code": role_code})
        return db_role

    def update(self, id: uuid.UUID, data: RoleUpdate) -> Role:
        db_role = self.db.get(Role, id)
        if not db_role:
            raise ValueError("Role not found")

        old_values = {}

        if data.name is not None and data.name != db_role.name:
            existing = self.db.scalar(select(Role).where(Role.name == data.name))
            if existing:
                raise ValueError("Role name already exists")
            role_code = data.name.strip().upper().replace(" ", "_")
            existing_code = self.db.scalar(select(Role).where(Role.role_code == role_code))
            if existing_code and existing_code.id != id:
                raise ValueError("Conflicting role code with another role")
            old_values["name"] = db_role.name
            old_values["role_code"] = db_role.role_code
            db_role.name = data.name
            db_role.role_code = role_code

        if data.description is not None:
            db_role.description = data.description
        if data.is_active is not None:
            if not data.is_active and db_role.child_roles:
                active_children = [c.name for c in db_role.child_roles if c.is_active]
                if active_children:
                    raise ValueError(
                        f"Cannot deactivate role '{db_role.name}' because it has active child roles: "
                        f"{', '.join(active_children)}. Deactivate child roles first."
                    )
            db_role.is_active = data.is_active

        if data.parent_role_id is not None:
            if data.parent_role_id == id:
                raise ValueError("A role cannot report to itself")
            parent = self.db.get(Role, data.parent_role_id)
            if not parent:
                raise ValueError("Parent role not found")
            # Cycle detection
            curr = parent
            while curr:
                if curr.id == id:
                    raise ValueError("Circular reporting hierarchy detected")
                curr = curr.parent_role
            db_role.parent_role_id = data.parent_role_id
            db_role.hierarchy_level = parent.hierarchy_level + 1
            update_child_hierarchies(self.db, db_role)
        elif "parent_role_id" in data.model_fields_set and data.parent_role_id is None:
            db_role.parent_role_id = None
            db_role.hierarchy_level = 1
            update_child_hierarchies(self.db, db_role)

        self.db.add(db_role)
        self.db.commit()
        self.db.refresh(db_role)

        AuditService.log(self.db, "role", id, "UPDATE",
                         old_value=old_values if old_values else None,
                         new_value={"name": db_role.name, "role_code": db_role.role_code})
        return db_role

    def delete(self, id: uuid.UUID) -> None:
        db_role = self.db.get(Role, id)
        if not db_role:
            raise ValueError("Role not found")
        if db_role.is_system_role:
            raise ValueError("System roles cannot be deleted")
        # Check if any employees are assigned this role
        assigned = self.db.scalar(
            select(EmployeeRole).where(EmployeeRole.role_id == id).limit(1)
        )
        if assigned:
            raise ValueError("Cannot delete role that is assigned to employees")
        # Re-parent children
        for child in db_role.child_roles:
            child.parent_role_id = db_role.parent_role_id
            child.hierarchy_level = db_role.hierarchy_level or 1
            self.db.add(child)
            update_child_hierarchies(self.db, child)
        self.db.delete(db_role)
        self.db.commit()
        AuditService.log(self.db, "role", id, "DELETE")
