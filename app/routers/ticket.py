import uuid
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.services.ticket_service import TicketService
from app.repositories.ticket_repository import TicketRepository
from app.models.employee import Employee

# Schemas
from app.schemas.ticket import (
    TicketCategoryCreate, TicketCategoryResponse,
    TicketTypeCreate, TicketTypeResponse,
    TicketPriorityResponse, TicketStatusResponse,
    TicketCategoryHandlerCreate, TicketCategoryHandlerResponse,
    TicketCreate, TicketResponse, TicketDetailResponse,
    TicketCommentCreate, TicketCommentResponse,
    TicketHistoryResponse, TicketAttachmentResponse
)

router = APIRouter(prefix="/tickets", tags=["Tickets"])

def _get_service(db: Session = Depends(get_db)) -> TicketService:
    return TicketService(db)

def _get_repo(db: Session = Depends(get_db)) -> TicketRepository:
    return TicketRepository(db)

# ── 1. Settings: Ticket Categories ────────────────────────────────────────────

@router.get(
    "/settings/categories",
    response_model=APIResponse,
    dependencies=[Depends(get_current_user)],
)
def get_categories(
    is_active: bool | None = Query(None),
    repo: TicketRepository = Depends(_get_repo),
):
    categories = repo.get_all_categories(is_active)
    return APIResponse(
        success=True,
        message="Ticket categories retrieved successfully",
        data={"categories": [TicketCategoryResponse.model_validate(c).model_dump() for c in categories]},
    )

@router.post(
    "/settings/categories",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "create"))],
)
def create_category(
    payload: TicketCategoryCreate,
    repo: TicketRepository = Depends(_get_repo),
):
    existing = repo.get_category_by_name(payload.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket category '{payload.name}' already exists",
        )
    cat = repo.create_category(payload.model_dump())
    return APIResponse(
        success=True,
        message="Ticket category created successfully",
        data={"category": TicketCategoryResponse.model_validate(cat).model_dump()},
    )

@router.put(
    "/settings/categories/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "update"))],
)
def update_category(
    id: uuid.UUID,
    payload: TicketCategoryCreate,
    repo: TicketRepository = Depends(_get_repo),
):
    cat = repo.get_category_by_id(id)
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket category not found",
        )
    
    # Check name collision
    existing = repo.get_category_by_name(payload.name)
    if existing and existing.id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket category '{payload.name}' already exists",
        )

    updated = repo.update_category(cat, payload.model_dump())
    return APIResponse(
        success=True,
        message="Ticket category updated successfully",
        data={"category": TicketCategoryResponse.model_validate(updated).model_dump()},
    )

@router.delete(
    "/settings/categories/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "delete"))],
)
def delete_category(
    id: uuid.UUID,
    repo: TicketRepository = Depends(_get_repo),
):
    cat = repo.get_category_by_id(id)
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket category not found",
        )
    repo.delete_category(cat)
    return APIResponse(
        success=True,
        message="Ticket category deleted successfully",
    )

# ── 2. Settings: Ticket Types ─────────────────────────────────────────────────

@router.get(
    "/settings/types",
    response_model=APIResponse,
    dependencies=[Depends(get_current_user)],
)
def get_types(
    category_id: uuid.UUID | None = Query(None),
    is_active: bool | None = Query(None),
    repo: TicketRepository = Depends(_get_repo),
):
    types = repo.get_all_types(category_id, is_active)
    return APIResponse(
        success=True,
        message="Ticket types retrieved successfully",
        data={"types": [TicketTypeResponse.model_validate(t).model_dump() for t in types]},
    )

@router.post(
    "/settings/types",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "create"))],
)
def create_type(
    payload: TicketTypeCreate,
    repo: TicketRepository = Depends(_get_repo),
):
    # Check category exists
    cat = repo.get_category_by_id(payload.category_id)
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target ticket category not found",
        )

    # Check duplicate
    existing_types = repo.get_all_types(payload.category_id)
    if any(t.name.lower() == payload.name.lower() for t in existing_types):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket type '{payload.name}' already exists in this category",
        )

    ttype = repo.create_type(payload.model_dump())
    return APIResponse(
        success=True,
        message="Ticket type created successfully",
        data={"type": TicketTypeResponse.model_validate(ttype).model_dump()},
    )

@router.put(
    "/settings/types/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "update"))],
)
def update_type(
    id: uuid.UUID,
    payload: TicketTypeCreate,
    repo: TicketRepository = Depends(_get_repo),
):
    ttype = repo.get_type_by_id(id)
    if not ttype:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket type not found",
        )

    # Check duplicate
    existing_types = repo.get_all_types(payload.category_id)
    if any(t.name.lower() == payload.name.lower() and t.id != id for t in existing_types):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket type '{payload.name}' already exists in this category",
        )

    updated = repo.update_type(ttype, payload.model_dump())
    return APIResponse(
        success=True,
        message="Ticket type updated successfully",
        data={"type": TicketTypeResponse.model_validate(updated).model_dump()},
    )

@router.delete(
    "/settings/types/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "delete"))],
)
def delete_type(
    id: uuid.UUID,
    repo: TicketRepository = Depends(_get_repo),
):
    ttype = repo.get_type_by_id(id)
    if not ttype:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket type not found",
        )
    repo.delete_type(ttype)
    return APIResponse(
        success=True,
        message="Ticket type deleted successfully",
    )

# ── 3. Settings: Ticket Priorities ────────────────────────────────────────────

@router.get(
    "/settings/priorities",
    response_model=APIResponse,
    dependencies=[Depends(get_current_user)],
)
def get_priorities(
    is_active: bool | None = Query(None),
    repo: TicketRepository = Depends(_get_repo),
):
    priorities = repo.get_all_priorities(is_active)
    return APIResponse(
        success=True,
        message="Ticket priorities retrieved successfully",
        data={"priorities": [TicketPriorityResponse.model_validate(p).model_dump() for p in priorities]},
    )

@router.post(
    "/settings/priorities",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "create"))],
)
def create_priority(
    name: str = Query(..., min_length=1, max_length=50),
    repo: TicketRepository = Depends(_get_repo),
):
    existing = repo.get_priority_by_name(name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket priority '{name}' already exists",
        )
    prio = repo.create_priority({"name": name, "is_active": True})
    return APIResponse(
        success=True,
        message="Ticket priority created successfully",
        data={"priority": TicketPriorityResponse.model_validate(prio).model_dump()},
    )

@router.put(
    "/settings/priorities/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "update"))],
)
def update_priority(
    id: uuid.UUID,
    name: str = Query(..., min_length=1, max_length=50),
    is_active: bool = Query(True),
    repo: TicketRepository = Depends(_get_repo),
):
    prio = repo.get_priority_by_id(id)
    if not prio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket priority not found",
        )
    
    existing = repo.get_priority_by_name(name)
    if existing and existing.id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket priority '{name}' already exists",
        )

    updated = repo.update_priority(prio, {"name": name, "is_active": is_active})
    return APIResponse(
        success=True,
        message="Ticket priority updated successfully",
        data={"priority": TicketPriorityResponse.model_validate(updated).model_dump()},
    )

@router.delete(
    "/settings/priorities/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "delete"))],
)
def delete_priority(
    id: uuid.UUID,
    repo: TicketRepository = Depends(_get_repo),
):
    prio = repo.get_priority_by_id(id)
    if not prio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket priority not found",
        )
    repo.delete_priority(prio)
    return APIResponse(
        success=True,
        message="Ticket priority deleted successfully",
    )

# ── 4. Settings: Ticket Statuses ──────────────────────────────────────────────

@router.get(
    "/settings/statuses",
    response_model=APIResponse,
    dependencies=[Depends(get_current_user)],
)
def get_statuses(
    is_active: bool | None = Query(None),
    repo: TicketRepository = Depends(_get_repo),
):
    statuses = repo.get_all_statuses(is_active)
    return APIResponse(
        success=True,
        message="Ticket statuses retrieved successfully",
        data={"statuses": [TicketStatusResponse.model_validate(s).model_dump() for s in statuses]},
    )

@router.post(
    "/settings/statuses",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "create"))],
)
def create_status(
    name: str = Query(..., min_length=1, max_length=50),
    repo: TicketRepository = Depends(_get_repo),
):
    existing = repo.get_status_by_name(name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket status '{name}' already exists",
        )
    stat = repo.create_status({"name": name, "is_active": True})
    return APIResponse(
        success=True,
        message="Ticket status created successfully",
        data={"status": TicketStatusResponse.model_validate(stat).model_dump()},
    )

@router.put(
    "/settings/statuses/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "update"))],
)
def update_status(
    id: uuid.UUID,
    name: str = Query(..., min_length=1, max_length=50),
    is_active: bool = Query(True),
    repo: TicketRepository = Depends(_get_repo),
):
    stat = repo.get_status_by_id(id)
    if not stat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket status not found",
        )
    
    existing = repo.get_status_by_name(name)
    if existing and existing.id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket status '{name}' already exists",
        )

    updated = repo.update_status(stat, {"name": name, "is_active": is_active})
    return APIResponse(
        success=True,
        message="Ticket status updated successfully",
        data={"status": TicketStatusResponse.model_validate(updated).model_dump()},
    )

@router.delete(
    "/settings/statuses/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "delete"))],
)
def delete_status(
    id: uuid.UUID,
    repo: TicketRepository = Depends(_get_repo),
):
    stat = repo.get_status_by_id(id)
    if not stat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket status not found",
        )
    repo.delete_status(stat)
    return APIResponse(
        success=True,
        message="Ticket status deleted successfully",
    )

# ── 5. Settings: Category Handlers ────────────────────────────────────────────

@router.get(
    "/settings/handlers",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "view"))],
)
def get_handlers(
    category_id: uuid.UUID | None = Query(None),
    repo: TicketRepository = Depends(_get_repo),
    db: Session = Depends(get_db),
):
    if category_id:
        handlers = repo.get_handlers_by_category(category_id)
    else:
        handlers = repo.get_all_handlers()

    handler_list = []
    for h in handlers:
        emp = db.get(Employee, h.employee_id)
        emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown Employee"
        handler_list.append({
            "id": h.id,
            "category_id": h.category_id,
            "employee_id": h.employee_id,
            "employee_name": emp_name,
            "is_active": h.is_active,
            "created_at": h.created_at,
        })

    return APIResponse(
        success=True,
        message="Ticket handlers retrieved successfully",
        data={"handlers": handler_list},
    )

@router.post(
    "/settings/handlers",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "create"))],
)
def create_handler(
    payload: TicketCategoryHandlerCreate,
    repo: TicketRepository = Depends(_get_repo),
    db: Session = Depends(get_db),
):
    cat = repo.get_category_by_id(payload.category_id)
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket category not found",
        )
    emp = db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    existing = repo.get_handler_by_category_and_employee(payload.category_id, payload.employee_id)
    if existing:
        if not existing.is_active:
            existing.is_active = True
            repo.save_ticket()
            h = existing
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This handler configuration already exists",
            )
    else:
        h = repo.create_handler(payload.category_id, payload.employee_id)

    emp_name = f"{emp.first_name} {emp.last_name}"
    
    return APIResponse(
        success=True,
        message="Category handler configured successfully",
        data={
            "handler": {
                "id": h.id,
                "category_id": h.category_id,
                "employee_id": h.employee_id,
                "employee_name": emp_name,
                "is_active": h.is_active,
                "created_at": h.created_at,
            }
        },
    )

@router.put(
    "/settings/handlers/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "edit"))],
)
def update_handler_status(
    id: uuid.UUID,
    is_active: bool = Query(True),
    repo: TicketRepository = Depends(_get_repo),
):
    h = repo.get_handler_by_id(id)
    if not h:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Handler configuration not found",
        )
    h.is_active = is_active
    repo.save_ticket()
    return APIResponse(
        success=True,
        message="Handler status updated successfully",
        data={
            "handler": {
                "id": h.id,
                "category_id": h.category_id,
                "employee_id": h.employee_id,
                "is_active": h.is_active,
                "updated_at": h.updated_at,
            }
        }
    )

@router.delete(
    "/settings/handlers/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("ticket_settings", "delete"))],
)
def delete_handler(
    id: uuid.UUID,
    repo: TicketRepository = Depends(_get_repo),
):
    h = repo.get_handler_by_id(id)
    if not h:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Handler configuration not found",
        )
    h.is_active = False
    repo.save_ticket()
    return APIResponse(
        success=True,
        message="Handler configuration deactivated successfully",
    )

# ── 6. Ticket Operations ──────────────────────────────────────────────────────

@router.get(
    "/my",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("my_tickets", "view"))],
)
def get_my_tickets_endpoint(
    current_user_id: str = Depends(get_current_user),
    service: TicketService = Depends(_get_service),
):
    user_uuid = uuid.UUID(current_user_id)
    tickets = service.get_my_tickets(user_uuid)
    
    ticket_list = []
    for t in tickets:
        ticket_list.append({
            "id": t.id,
            "ticket_number": t.ticket_number,
            "category_id": t.category_id,
            "category_name": t.category.name if t.category else None,
            "ticket_type_id": t.ticket_type_id,
            "ticket_type_name": t.ticket_type.name if t.ticket_type else None,
            "subject": t.subject,
            "status_id": t.status_id,
            "status_name": t.status.name if t.status else None,
            "priority_id": t.priority_id,
            "priority_name": t.priority.name if t.priority else None,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })

    return APIResponse(
        success=True,
        message="My tickets retrieved successfully",
        data={"tickets": ticket_list},
    )

@router.post(
    "/my",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("raise_ticket", "create"))],
)
def raise_ticket_endpoint(
    payload: TicketCreate,
    current_user_id: str = Depends(get_current_user),
    service: TicketService = Depends(_get_service),
):
    user_uuid = uuid.UUID(current_user_id)
    try:
        attachments_dicts = []
        if payload.attachments:
            attachments_dicts = [a.model_dump() for a in payload.attachments]
        
        ticket = service.raise_ticket(
            raised_by_id=user_uuid,
            data=payload.model_dump(),
            attachments_data=attachments_dicts
        )
        return APIResponse(
            success=True,
            message="Ticket raised successfully",
            data={
                "ticket": {
                    "id": ticket.id,
                    "ticket_number": ticket.ticket_number,
                }
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

@router.get(
    "/category",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("category_tickets", "view"))],
)
def get_category_tickets_endpoint(
    current_user_id: str = Depends(get_current_user),
    service: TicketService = Depends(_get_service),
    db: Session = Depends(get_db),
):
    user_uuid = uuid.UUID(current_user_id)
    
    # Check if user is super admin
    from app.services.auth_engine_service import AuthorizationEngine
    auth_eng = AuthorizationEngine(db)
    is_super = auth_eng._is_super_admin(user_uuid)

    tickets = service.get_category_tickets(user_uuid, is_super_admin=is_super)
    
    ticket_list = []
    for t in tickets:
        raised_emp = db.get(Employee, t.raised_by_id)
        raised_name = f"{raised_emp.first_name} {raised_emp.last_name}" if raised_emp else "Unknown"
        ticket_list.append({
            "id": t.id,
            "ticket_number": t.ticket_number,
            "category_id": t.category_id,
            "category_name": t.category.name if t.category else None,
            "ticket_type_id": t.ticket_type_id,
            "ticket_type_name": t.ticket_type.name if t.ticket_type else None,
            "subject": t.subject,
            "status_id": t.status_id,
            "status_name": t.status.name if t.status else None,
            "priority_id": t.priority_id,
            "priority_name": t.priority.name if t.priority else None,
            "raised_by_id": t.raised_by_id,
            "raised_by_name": raised_name,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })

    return APIResponse(
        success=True,
        message="Category tickets retrieved successfully",
        data={"tickets": ticket_list},
    )

@router.get(
    "/is-handler",
    response_model=APIResponse,
)
def check_is_handler(
    current_user_id: str = Depends(get_current_user),
    service: TicketService = Depends(_get_service),
    db: Session = Depends(get_db),
):
    user_uuid = uuid.UUID(current_user_id)
    from app.services.auth_engine_service import AuthorizationEngine
    auth_eng = AuthorizationEngine(db)
    is_super = auth_eng._is_super_admin(user_uuid)
    
    is_handler = is_super or service.is_employee_handler(user_uuid)
    return APIResponse(
        success=True,
        data={"is_handler": is_handler},
    )

@router.get(
    "/{id}",
    response_model=APIResponse,
)
def get_ticket_details_endpoint(
    id: uuid.UUID,
    current_user_id: str = Depends(get_current_user),
    service: TicketService = Depends(_get_service),
    db: Session = Depends(get_db),
):
    user_uuid = uuid.UUID(current_user_id)
    from app.services.auth_engine_service import AuthorizationEngine
    auth_eng = AuthorizationEngine(db)
    is_super = auth_eng._is_super_admin(user_uuid)

    try:
        t = service.get_ticket_details(id, user_uuid, is_super_admin=is_super)
        
        # Load related data details
        raised_emp = db.get(Employee, t.raised_by_id)
        raised_name = f"{raised_emp.first_name} {raised_emp.last_name}" if raised_emp else "Unknown"

        # Comments
        comments = []
        for c in t.comments:
            c_emp = db.get(Employee, c.commented_by_id)
            c_name = f"{c_emp.first_name} {c_emp.last_name}" if c_emp else "Unknown"
            comments.append({
                "id": c.id,
                "comment": c.comment,
                "commented_by_id": c.commented_by_id,
                "commented_by_name": c_name,
                "created_at": c.created_at,
            })
        # Sort comments oldest to newest
        comments.sort(key=lambda x: x["created_at"])

        # History
        history = []
        for h in t.history:
            h_emp = db.get(Employee, h.performed_by_id)
            h_name = f"{h_emp.first_name} {h_emp.last_name}" if h_emp else "Unknown"
            history.append({
                "id": h.id,
                "action": h.action,
                "field_name": h.field_name,
                "previous_value": h.previous_value,
                "new_value": h.new_value,
                "performed_by_id": h.performed_by_id,
                "performed_by_name": h_name,
                "created_at": h.created_at,
            })
        # Sort history oldest to newest
        history.sort(key=lambda x: x["created_at"])

        # Attachments
        attachments = []
        for a in t.attachments:
            attachments.append({
                "id": a.id,
                "filename": a.filename,
                "file_url": a.file_url,
                "uploaded_by_id": a.uploaded_by_id,
                "created_at": a.created_at,
            })

        detail = {
            "id": t.id,
            "ticket_number": t.ticket_number,
            "category_id": t.category_id,
            "category_name": t.category.name if t.category else None,
            "ticket_type_id": t.ticket_type_id,
            "ticket_type_name": t.ticket_type.name if t.ticket_type else None,
            "subject": t.subject,
            "description": t.description,
            "priority_id": t.priority_id,
            "priority_name": t.priority.name if t.priority else None,
            "status_id": t.status_id,
            "status_name": t.status.name if t.status else None,
            "raised_by_id": t.raised_by_id,
            "raised_by_name": raised_name,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "attachments": attachments,
            "comments": comments,
            "history": history,
        }

        return APIResponse(
            success=True,
            message="Ticket details retrieved successfully",
            data={"ticket": detail},
        )
    except ValueError as e:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_403_FORBIDDEN
        raise HTTPException(
            status_code=status_code,
            detail=str(e),
        )

@router.put(
    "/{id}/status",
    response_model=APIResponse,
)
def update_ticket_status_endpoint(
    id: uuid.UUID,
    status_id: uuid.UUID = Query(...),
    current_user_id: str = Depends(get_current_user),
    service: TicketService = Depends(_get_service),
    db: Session = Depends(get_db),
):
    user_uuid = uuid.UUID(current_user_id)
    from app.services.auth_engine_service import AuthorizationEngine
    auth_eng = AuthorizationEngine(db)
    is_super = auth_eng._is_super_admin(user_uuid)

    try:
        service.update_ticket_status(id, user_uuid, status_id, is_super_admin=is_super)
        return APIResponse(
            success=True,
            message="Ticket status updated successfully",
        )
    except ValueError as e:
        status_code = status.HTTP_400_BAD_REQUEST if "not found" not in str(e).lower() else status.HTTP_404_NOT_FOUND
        if "access denied" in str(e).lower():
            status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(
            status_code=status_code,
            detail=str(e),
        )

@router.post(
    "/{id}/comments",
    response_model=APIResponse,
)
def add_comment_endpoint(
    id: uuid.UUID,
    payload: TicketCommentCreate,
    current_user_id: str = Depends(get_current_user),
    service: TicketService = Depends(_get_service),
    db: Session = Depends(get_db),
):
    user_uuid = uuid.UUID(current_user_id)
    from app.services.auth_engine_service import AuthorizationEngine
    auth_eng = AuthorizationEngine(db)
    is_super = auth_eng._is_super_admin(user_uuid)

    try:
        comment = service.add_comment(
            ticket_id=id,
            commented_by_id=user_uuid,
            comment_text=payload.comment,
            is_super_admin=is_super
        )
        
        emp = db.get(Employee, comment.commented_by_id)
        emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"

        return APIResponse(
            success=True,
            message="Comment posted successfully",
            data={
                "comment": {
                    "id": comment.id,
                    "comment": comment.comment,
                    "commented_by_id": comment.commented_by_id,
                    "commented_by_name": emp_name,
                    "created_at": comment.created_at,
                }
            },
        )
    except ValueError as e:
        status_code = status.HTTP_400_BAD_REQUEST if "not found" not in str(e).lower() else status.HTTP_404_NOT_FOUND
        if "access denied" in str(e).lower():
            status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(
            status_code=status_code,
            detail=str(e),
        )

# ── 7. File Upload & Serve ────────────────────────────────────────────────────

@router.post("/upload", response_model=APIResponse)
def upload_ticket_attachment(
    file: UploadFile = File(...),
):
    uploads_dir = os.path.join(os.getcwd(), "uploads", "ticket_attachments")
    os.makedirs(uploads_dir, exist_ok=True)

    file_id = uuid.uuid4()
    extension = os.path.splitext(file.filename)[1]
    filename = f"{file_id}{extension}"
    filepath = os.path.join(uploads_dir, filename)

    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )

    return APIResponse(
        success=True,
        message="Attachment uploaded successfully",
        data={
            "filename": file.filename,
            "url": f"/api/v1/tickets/document/{filename}",
            "file_url": f"/api/v1/tickets/document/{filename}"
        }
    )

@router.get("/document/{filename}")
def get_ticket_attachment(filename: str):
    uploads_dir = os.path.abspath(os.path.join(os.getcwd(), "uploads", "ticket_attachments"))
    filepath = os.path.abspath(os.path.join(uploads_dir, filename))
    
    # Path traversal prevention check
    if not filepath.startswith(uploads_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
        
    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file not found",
        )
    return FileResponse(filepath)
