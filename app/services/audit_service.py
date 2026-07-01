import uuid
import logging
from datetime import datetime, timezone

from app.models.audit_log import AuditLog
from app.middleware.audit_context import get_audit_context

logger = logging.getLogger("uvicorn.error")


class AuditService:
    """Shared utility for recording audit log entries."""

    @staticmethod
    def _make_json_serializable(data):
        import uuid
        from datetime import date, datetime
        from decimal import Decimal

        if data is None:
            return None
        if isinstance(data, dict):
            return {str(k): AuditService._make_json_serializable(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [AuditService._make_json_serializable(item) for item in data]
        elif isinstance(data, uuid.UUID):
            return str(data)
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        return data

    @staticmethod
    def log(
        db,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        performed_by: uuid.UUID | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        ctx_ip, ctx_ua = get_audit_context()
        
        # Ensure values are JSON serializable (converts UUIDs and dates/datetimes to strings)
        serialized_old = AuditService._make_json_serializable(old_value)
        serialized_new = AuditService._make_json_serializable(new_value)

        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=serialized_old,
            new_value=serialized_new,
            performed_by=performed_by,
            ip_address=ip_address or ctx_ip,
            user_agent=user_agent or ctx_ua,
            performed_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        db.flush()  # Changed from db.commit() - callers own the transaction boundary

        # Log to the console for real-time visibility
        detail_str = ""
        if new_value:
            name = new_value.get("name") or new_value.get("role_code") or new_value.get("email") or new_value.get("employee_code")
            if name:
                detail_str = f" - {name}"
        logger.info(f"[Audit] [{action.upper()}] {entity_type.upper()} {entity_id}{detail_str}")

        return entry

