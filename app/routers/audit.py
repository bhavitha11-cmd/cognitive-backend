from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.audit_log import AuditLog
from app.schemas.common import APIResponse

from app.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"],
    dependencies=[Depends(get_current_user), Depends(require_permission("HR", "view"))],
)


@router.get("", response_model=APIResponse)
def list_audit_logs(
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = []
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if entity_id:
        filters.append(AuditLog.entity_id == entity_id)
    if action:
        filters.append(AuditLog.action == action)

    base_query = select(AuditLog)
    if filters:
        base_query = base_query.where(*filters)

    total_count = db.scalar(
        select(func.count()).select_from(base_query.subquery())
    ) or 0

    offset = (page - 1) * size
    logs = db.scalars(
        base_query.order_by(AuditLog.performed_at.desc()).offset(offset).limit(size)
    ).all()

    result = []
    for log in logs:
        performer_name = None
        if log.performer:
            performer_name = f"{log.performer.first_name} {log.performer.last_name}"
        result.append({
            "id": str(log.id),
            "entity_type": log.entity_type,
            "entity_id": str(log.entity_id),
            "action": log.action,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "performed_by": str(log.performed_by) if log.performed_by else None,
            "performer_name": performer_name,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "performed_at": log.performed_at.isoformat(),
        })

    return APIResponse(
        success=True,
        message="Audit logs retrieved",
        data={
            "logs": result,
            "total": total_count,
            "page": page,
            "size": size,
        },
    )
