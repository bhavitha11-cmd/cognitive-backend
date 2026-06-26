import re
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.task_template import TaskTemplate
from app.schemas.task_template import (
    TaskTemplateCreate,
    TaskTemplateResponse,
    TaskTemplateSearchItem,
    TaskTemplateUpdate,
)
from app.services.audit_service import AuditService


class TaskTemplateService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _generate_code(self) -> str:
        max_code = self.db.scalar(
            select(func.max(TaskTemplate.template_code))
        )
        if max_code:
            match = re.search(r"(\d+)$", max_code)
            if match:
                next_num = int(match.group(1)) + 1
                return f"TT-{next_num:05d}"
        return "TT-00001"

    def _check_duplicate_title(self, title: str, exclude_id: UUID | None = None) -> bool:
        stmt = select(TaskTemplate).where(
            func.lower(TaskTemplate.title) == title.lower().strip(),
            TaskTemplate.is_active == True,
        )
        if exclude_id:
            stmt = stmt.where(TaskTemplate.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def _to_response(self, template: TaskTemplate) -> TaskTemplateResponse:
        return TaskTemplateResponse.model_validate(template)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[TaskTemplateResponse], int]:
        stmt = select(TaskTemplate)

        if search:
            stmt = stmt.where(
                TaskTemplate.title.ilike(f"%{search.strip()}%")
            )
        if is_active is not None:
            stmt = stmt.where(TaskTemplate.is_active == is_active)

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        # Sort
        sort_col = getattr(TaskTemplate, sort_by, TaskTemplate.created_at)
        if sort_order == "asc":
            stmt = stmt.order_by(sort_col.asc())
        else:
            stmt = stmt.order_by(sort_col.desc())

        stmt = stmt.offset(skip).limit(limit)
        templates = list(self.db.scalars(stmt).all())
        return [self._to_response(t) for t in templates], total

    def get_by_id(self, id: UUID) -> TaskTemplateResponse:
        template = self.db.get(TaskTemplate, id)
        if not template:
            raise ValueError(f"Task template with id {id} not found")
        return self._to_response(template)

    def create(self, data: TaskTemplateCreate) -> TaskTemplateResponse:
        title = data.title.strip()
        if self._check_duplicate_title(title):
            raise ValueError(
                f"A task template with title '{title}' already exists"
            )

        template = TaskTemplate(
            template_code=self._generate_code(),
            title=title,
            description=data.description.strip() if data.description else None,
            created_by=self.current_user_id,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        AuditService.log(
            self.db, "task_template", template.id, "CREATE",
            performed_by=self.current_user_id,
            new_value={"template_code": template.template_code, "title": template.title},
        )
        return self._to_response(template)

    def update(self, id: UUID, data: TaskTemplateUpdate) -> TaskTemplateResponse:
        template = self.db.get(TaskTemplate, id)
        if not template:
            raise ValueError(f"Task template with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        if "title" in update_data:
            new_title = update_data["title"].strip()
            if new_title.lower() != template.title.lower():
                if self._check_duplicate_title(new_title, exclude_id=id):
                    raise ValueError(
                        f"A task template with title '{new_title}' already exists"
                    )
            template.title = new_title

        if "description" in update_data:
            template.description = update_data["description"].strip() if update_data["description"] else None

        if "is_active" in update_data:
            template.is_active = update_data["is_active"]

        template.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(template)

        AuditService.log(
            self.db, "task_template", id, "UPDATE",
            performed_by=self.current_user_id,
            old_value={"title": template.title},
            new_value=update_data,
        )
        return self._to_response(template)

    def delete(self, id: UUID) -> None:
        template = self.db.get(TaskTemplate, id)
        if not template:
            raise ValueError(f"Task template with id {id} not found")

        template.is_active = False
        template.updated_by = self.current_user_id
        self.db.commit()

        AuditService.log(
            self.db, "task_template", id, "DELETE",
            performed_by=self.current_user_id,
            old_value={"template_code": template.template_code, "title": template.title},
        )

    def bulk_status(self, ids: list[UUID], is_active: bool) -> int:
        templates = self.db.scalars(
            select(TaskTemplate).where(TaskTemplate.id.in_(ids))
        ).all()
        count = 0
        for t in templates:
            if t.is_active != is_active:
                t.is_active = is_active
                t.updated_by = self.current_user_id
                count += 1
        self.db.commit()

        for t in templates:
            AuditService.log(
                self.db, "task_template", t.id,
                "ACTIVATE" if is_active else "DEACTIVATE",
                performed_by=self.current_user_id,
                old_value={"is_active": not is_active},
                new_value={"is_active": is_active},
            )
        return count

    def search(self, q: str | None = None) -> list[TaskTemplateSearchItem]:
        stmt = select(TaskTemplate).where(TaskTemplate.is_active == True)
        if q:
            stmt = stmt.where(TaskTemplate.title.ilike(f"%{q.strip()}%"))
        stmt = stmt.order_by(TaskTemplate.title.asc()).limit(50)
        templates = list(self.db.scalars(stmt).all())
        return [TaskTemplateSearchItem.model_validate(t) for t in templates]
