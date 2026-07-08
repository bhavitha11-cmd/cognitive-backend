"""
Module & Feature Registry API.

GET /modules          → list all active modules with their features
GET /modules/{id}     → get a single module with features

These endpoints power the permission matrix UI and sidebar generation.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.session import get_db
from app.dependencies import get_current_user
from app.models.module import Module
from app.schemas.common import APIResponse
from app.schemas.role import ModuleResponse

router = APIRouter(
    prefix="/modules",
    tags=["Modules"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=APIResponse)
def get_modules(db: Session = Depends(get_db)):
    """Return all active modules with their active features."""
    modules = db.scalars(
        select(Module)
        .options(selectinload(Module.features))
        .where(Module.is_active == True)
        .order_by(Module.display_order)
    ).unique().all()

    return APIResponse(
        success=True,
        message="Modules retrieved successfully",
        data={
            "modules": [ModuleResponse.model_validate(m).model_dump() for m in modules],
        },
    )


@router.get("/{module_id}", response_model=APIResponse)
def get_module(module_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return a single module with its features."""
    module = db.scalars(
        select(Module)
        .options(selectinload(Module.features))
        .where(Module.id == module_id, Module.is_active == True)
    ).unique().first()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    return APIResponse(
        success=True,
        message="Module retrieved successfully",
        data={"module": ModuleResponse.model_validate(module).model_dump()},
    )
