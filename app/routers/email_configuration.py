from __future__ import annotations

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.email_configuration import EmailConfiguration
from app.models.employee import Employee
from app.services.email_service import EmailService
from app.core.encryption import encrypt_value
from app.schemas.common import APIResponse

router = APIRouter(
    prefix="/settings/email-configurations",
    tags=["Email Configurations"],
    dependencies=[Depends(get_current_user)],
)


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class EmailConfigurationResponse(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    sender_email: str
    is_active: bool
    connection_status: str
    last_tested_at: datetime | None = None
    error_message: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_has_password: bool
    smtp_use_tls: bool
    tenant_id: str | None = None
    client_id: str | None = None
    graph_has_secret: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmailConfigurationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field("microsoft_graph", pattern="^(microsoft_graph|smtp)$")
    sender_email: EmailStr
    is_active: bool = False
    smtp_host: str | None = Field(None, max_length=255)
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_username: str | None = Field(None, max_length=255)
    smtp_password: str | None = Field(None, max_length=255)
    smtp_use_tls: bool = True
    tenant_id: str | None = Field(None, max_length=255)
    client_id: str | None = Field(None, max_length=255)
    client_secret: str | None = Field(None, max_length=255)


class EmailConfigurationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    provider: str | None = Field(None, pattern="^(microsoft_graph|smtp)$")
    sender_email: EmailStr | None = None
    is_active: bool | None = None
    smtp_host: str | None = Field(None, max_length=255)
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_username: str | None = Field(None, max_length=255)
    smtp_password: str | None = Field(None, max_length=255)
    smtp_use_tls: bool | None = None
    tenant_id: str | None = Field(None, max_length=255)
    client_id: str | None = Field(None, max_length=255)
    client_secret: str | None = Field(None, max_length=255)


class TestConnectionRequest(BaseModel):
    name: str = "Test Mailbox"
    provider: str = Field("microsoft_graph", pattern="^(microsoft_graph|smtp)$")
    sender_email: EmailStr
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    test_recipient: EmailStr | None = None


# ─── Helper Functions ─────────────────────────────────────────────────────────

def to_response_model(config: EmailConfiguration) -> dict:
    """Helper to convert model to response dictionary with custom has_password attributes."""
    data = {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "sender_email": config.sender_email,
        "is_active": config.is_active,
        "connection_status": config.connection_status,
        "last_tested_at": config.last_tested_at,
        "error_message": config.error_message,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_username": config.smtp_username,
        "smtp_has_password": bool(config.smtp_password),
        "smtp_use_tls": config.smtp_use_tls,
        "tenant_id": config.tenant_id,
        "client_id": config.client_id,
        "graph_has_secret": bool(config.client_secret),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }
    return data


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "view"))],
)
def list_email_configurations(db: Session = Depends(get_db)):
    """List all email configurations."""
    configs = db.scalars(
        select(EmailConfiguration).order_by(EmailConfiguration.created_at.desc())
    ).all()
    
    return APIResponse(
        success=True,
        message="Email configurations retrieved",
        data={"configurations": [to_response_model(c) for c in configs]},
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def create_email_configuration(
    data: EmailConfigurationCreate,
    db: Session = Depends(get_db),
):
    """Create a new email configuration."""
    # If this is set as active, deactivate other configurations first
    if data.is_active:
        db.execute(
            update(EmailConfiguration)
            .where(EmailConfiguration.is_active == True)
            .values(is_active=False)
        )

    # Encrypt password / secret if provided
    encrypted_smtp_password = encrypt_value(data.smtp_password) if data.smtp_password else None
    encrypted_client_secret = encrypt_value(data.client_secret) if data.client_secret else None

    new_config = EmailConfiguration(
        name=data.name,
        provider=data.provider,
        sender_email=data.sender_email,
        is_active=data.is_active,
        smtp_host=data.smtp_host,
        smtp_port=data.smtp_port,
        smtp_username=data.smtp_username,
        smtp_password=encrypted_smtp_password,
        smtp_use_tls=data.smtp_use_tls,
        tenant_id=data.tenant_id,
        client_id=data.client_id,
        client_secret=encrypted_client_secret,
        connection_status="untested",
    )

    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    return APIResponse(
        success=True,
        message="Email configuration created successfully",
        data=to_response_model(new_config),
    )


@router.put(
    "/{config_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def update_email_configuration(
    config_id: uuid.UUID,
    data: EmailConfigurationUpdate,
    db: Session = Depends(get_db),
):
    """Update an existing email configuration."""
    config = db.scalar(
        select(EmailConfiguration).where(EmailConfiguration.id == config_id)
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email configuration not found",
        )

    # If setting as active, deactivate all other configs
    if data.is_active is True:
        db.execute(
            update(EmailConfiguration)
            .where(EmailConfiguration.is_active == True)
            .values(is_active=False)
        )

    update_dict = data.model_dump(exclude_unset=True)

    # Handle encryption for password/secret updates specifically
    if "smtp_password" in update_dict:
        if update_dict["smtp_password"]:
            update_dict["smtp_password"] = encrypt_value(update_dict["smtp_password"])
        else:
            # If explicit None or empty, preserve existing or clear it
            update_dict["smtp_password"] = None
            
    if "client_secret" in update_dict:
        if update_dict["client_secret"]:
            update_dict["client_secret"] = encrypt_value(update_dict["client_secret"])
        else:
            update_dict["client_secret"] = None

    # Apply changes
    for field, val in update_dict.items():
        setattr(config, field, val)

    # When config is updated, we reset connection status to untested since settings changed
    # (unless the update only changed active status or name)
    changed_keys = set(update_dict.keys())
    config_keys = {"provider", "sender_email", "smtp_host", "smtp_port", "smtp_username", "smtp_password", "tenant_id", "client_id", "client_secret"}
    if changed_keys.intersection(config_keys):
        config.connection_status = "untested"
        config.error_message = None

    db.commit()
    db.refresh(config)

    return APIResponse(
        success=True,
        message="Email configuration updated successfully",
        data=to_response_model(config),
    )


@router.delete(
    "/{config_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def delete_email_configuration(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Delete an email configuration. Prevents deleting the active configuration."""
    config = db.scalar(
        select(EmailConfiguration).where(EmailConfiguration.id == config_id)
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email configuration not found",
        )

    if config.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the currently active email configuration. Please activate another configuration first.",
        )

    db.delete(config)
    db.commit()

    return APIResponse(
        success=True,
        message="Email configuration deleted successfully",
    )


@router.post(
    "/{config_id}/activate",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def activate_email_configuration(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Activate a specific email configuration and deactivate all others."""
    config = db.scalar(
        select(EmailConfiguration).where(EmailConfiguration.id == config_id)
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email configuration not found",
        )

    # Deactivate all configurations
    db.execute(
        update(EmailConfiguration)
        .where(EmailConfiguration.is_active == True)
        .values(is_active=False)
    )

    # Activate selected one
    config.is_active = True
    db.commit()
    db.refresh(config)

    return APIResponse(
        success=True,
        message=f"Email configuration '{config.name}' is now active.",
        data=to_response_model(config),
    )


@router.post(
    "/test",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def test_unsaved_configuration(
    data: TestConnectionRequest,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test connection using unsaved configuration details (e.g. from UI before saving)."""
    # 1. Resolve test recipient (default to current admin's email or sender_email)
    recipient = data.test_recipient
    if not recipient:
        user_uuid = uuid.UUID(current_user_id)
        admin_employee = db.scalar(select(Employee).where(Employee.id == user_uuid))
        if admin_employee and admin_employee.email:
            recipient = admin_employee.email
        else:
            recipient = data.sender_email

    # 2. Instantiate temporary (unsaved) EmailConfiguration object for test
    temp_config = EmailConfiguration(
        name=data.name,
        provider=data.provider,
        sender_email=data.sender_email,
        smtp_host=data.smtp_host,
        smtp_port=data.smtp_port,
        smtp_username=data.smtp_username,
        smtp_password=encrypt_value(data.smtp_password) if data.smtp_password else None,
        smtp_use_tls=data.smtp_use_tls,
        tenant_id=data.tenant_id,
        client_id=data.client_id,
        client_secret=encrypt_value(data.client_secret) if data.client_secret else None,
    )

    # 3. Test connection (temp_config is not in DB session, so test_connection won't commit it)
    success, error_msg = EmailService.test_connection(db, temp_config, recipient)

    return APIResponse(
        success=success,
        message="Connection test completed" if success else f"Connection test failed: {error_msg}",
        data={
            "success": success,
            "error_message": error_msg,
            "recipient": recipient,
        },
    )


@router.post(
    "/{config_id}/test",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def test_saved_configuration(
    config_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test connection using an already saved configuration by its ID."""
    config = db.scalar(
        select(EmailConfiguration).where(EmailConfiguration.id == config_id)
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email configuration not found",
        )

    # 1. Resolve test recipient (default to current admin's email or sender_email)
    user_uuid = uuid.UUID(current_user_id)
    admin_employee = db.scalar(select(Employee).where(Employee.id == user_uuid))
    recipient = admin_employee.email if (admin_employee and admin_employee.email) else config.sender_email

    # 2. Test connection and commit results
    success, error_msg = EmailService.test_connection(db, config, recipient)

    return APIResponse(
        success=success,
        message="Connection test completed" if success else f"Connection test failed: {error_msg}",
        data={
            "success": success,
            "error_message": error_msg,
            "recipient": recipient,
            "config": to_response_model(config),
        },
    )
