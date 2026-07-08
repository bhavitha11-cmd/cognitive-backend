from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.role import Role
from app.schemas.common import APIResponse
from app.services.employee_service import EmployeeService
from sqlalchemy import select

from app.dependencies import get_current_user, require_permission
from app.core.rbac import require_data_access, UserContext

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


@router.get("/{employee_id}/manager-chain", response_model=APIResponse)
def get_manager_chain(employee_id: UUID, db: Session = Depends(get_db)):
    from app.services.organization_hierarchy_service import OrganizationHierarchyService
    service = OrganizationHierarchyService(db)
    chain = service.get_manager_chain(employee_id)
    return APIResponse(
        success=True,
        message="Manager chain retrieved",
        data={
            "employee_id": str(employee_id),
            "chain": [c.model_dump() for c in chain],
            "chain_length": len(chain)
        }
    )


@router.get("/{employee_id}/subordinates", response_model=APIResponse)
def get_subordinates(
    employee_id: UUID,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
):
    from app.services.organization_hierarchy_service import OrganizationHierarchyService
    
    is_hr = False
    if user_ctx.is_super_admin or "HR" in user_ctx.role_codes or "ADMIN" in user_ctx.role_codes:
        is_hr = True
        
    requester_id = user_ctx.employee_id
    
    if not is_hr and requester_id != employee_id:
        service = OrganizationHierarchyService(db)
        if not service.is_manager_of(requester_id, employee_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view this employee's subordinates."
            )

    service = OrganizationHierarchyService(db)
    subordinates = service.get_subordinates(employee_id)
    return APIResponse(
        success=True,
        message="Subordinates retrieved",
        data={
            "employee_id": str(employee_id),
            "subordinates": [s.model_dump() for s in subordinates],
            "count": len(subordinates)
        }
    )
