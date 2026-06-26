from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.schemas.calendar import (
    CompanyEventCreate,
    CompanyEventResponse,
    CompanyEventUpdate,
)


class CompanyEventService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        from_date: date | None = None,
        to_date: date | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[CompanyEventResponse], int]:
        stmt = select(CalendarEvent).where(
            CalendarEvent.event_type == "COMPANY_EVENT"
        )

        if from_date:
            stmt = stmt.where(CalendarEvent.start_date >= from_date)
        if to_date:
            stmt = stmt.where(CalendarEvent.start_date <= to_date)
        if is_active is not None:
            stmt = stmt.where(CalendarEvent.is_active == is_active)

        count_stmt = select(sa_func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = stmt.order_by(CalendarEvent.start_date.desc()).offset(skip).limit(limit)
        events = self.db.scalars(stmt).all()
        return [CompanyEventResponse.model_validate(e) for e in events], total

    def get_by_id(self, id: uuid.UUID) -> CompanyEventResponse:
        event = self.db.get(CalendarEvent, id)
        if not event or event.event_type != "COMPANY_EVENT":
            raise ValueError(f"Company event with id {id} not found")
        return CompanyEventResponse.model_validate(event)

    def create(self, data: CompanyEventCreate) -> CompanyEventResponse:
        event = CalendarEvent(
            title=data.title,
            description=data.description,
            event_type="COMPANY_EVENT",
            event_subtype=data.event_subtype,
            start_date=data.start_date,
            end_date=data.end_date,
            start_time=data.start_time,
            end_time=data.end_time,
            is_all_day=data.is_all_day,
            color=data.color or "#8B5CF6",
            text_color=data.text_color or "#ffffff",
            is_active=True,
            created_by=self.current_user_id,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return CompanyEventResponse.model_validate(event)

    def update(self, id: uuid.UUID, data: CompanyEventUpdate) -> CompanyEventResponse:
        event = self.db.get(CalendarEvent, id)
        if not event or event.event_type != "COMPANY_EVENT":
            raise ValueError(f"Company event with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(event, field, value)

        self.db.commit()
        self.db.refresh(event)
        return CompanyEventResponse.model_validate(event)

    def delete(self, id: uuid.UUID) -> None:
        event = self.db.get(CalendarEvent, id)
        if not event or event.event_type != "COMPANY_EVENT":
            raise ValueError(f"Company event with id {id} not found")

        event.is_active = False
        self.db.commit()
