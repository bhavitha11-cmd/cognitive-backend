from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.role import Role
from app.schemas.common import APIResponse
from app.services.employee_service import EmployeeService
from sqlalchemy import select

from app.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/organization",
    tags=["Organization"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/tree", response_model=APIResponse,
            dependencies=[Depends(require_permission("HR", "view"))])
def get_employee_org_tree(db: Session = Depends(get_db)):
    service = EmployeeService(db)
    tree = service.get_organization_tree()
    return APIResponse(
        success=True,
        message="Organization tree retrieved",
        data={"tree": tree},
    )


@router.get("/tree/role", response_model=APIResponse,
            dependencies=[Depends(require_permission("HR", "view"))])
def get_role_hierarchy_tree(db: Session = Depends(get_db)):
    roles = db.scalars(
        select(Role).where(Role.is_active == True).order_by(Role.hierarchy_level)
    ).all()

    role_map = {r.id: r for r in roles}
    children_map: dict = {}
    roots = []
    for r in roles:
        if r.parent_role_id and r.parent_role_id in role_map:
            children_map.setdefault(r.parent_role_id, []).append(r)
        else:
            roots.append(r)

    def build_node(role: Role) -> dict:
        node = {
            "id": str(role.id),
            "label": role.name,
            "role_code": role.role_code,
            "hierarchy_level": role.hierarchy_level,
            "is_system_role": role.is_system_role,
            "children": [],
        }
        for child in children_map.get(role.id, []):
            node["children"].append(build_node(child))
        return node

    tree = [build_node(r) for r in roots]
    return APIResponse(
        success=True,
        message="Role hierarchy tree retrieved",
        data={"tree": tree},
    )
