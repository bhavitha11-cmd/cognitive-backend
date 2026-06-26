from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.schemas.holiday import HolidayCreate, HolidayResponse, HolidayUpdate
from app.services.audit_service import AuditService
from app.services.recalculation_engine import RecalculationEngine


class HolidayService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        year: int | None = None,
        holiday_type: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        sort_by: str = "date",
        sort_order: str = "asc",
    ) -> tuple[list[HolidayResponse], int]:
        stmt = select(Holiday)

        if year:
            stmt = stmt.where(sa_func.extract("year", Holiday.date) == year)
        if holiday_type:
            stmt = stmt.where(Holiday.holiday_type == holiday_type)
        if is_active is not None:
            stmt = stmt.where(Holiday.is_active == is_active)
        if search:
            stmt = stmt.where(Holiday.name.ilike(f"%{search}%"))
        if from_date:
            stmt = stmt.where(Holiday.date >= from_date)
        if to_date:
            stmt = stmt.where(Holiday.date <= to_date)

        count_stmt = select(sa_func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        sort_column = getattr(Holiday, sort_by, Holiday.date)
        if sort_order == "desc":
            sort_column = sort_column.desc()
        stmt = stmt.order_by(sort_column).offset(skip).limit(limit)

        holidays = self.db.scalars(stmt).all()
        return [HolidayResponse.model_validate(h) for h in holidays], total

    def get_by_id(self, id: uuid.UUID) -> HolidayResponse:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")
        return HolidayResponse.model_validate(holiday)

    def create(self, data: HolidayCreate) -> HolidayResponse:
        existing = self.db.scalar(
            select(Holiday).where(Holiday.date == data.date)
        )
        if existing:
            raise ValueError(
                f"A holiday already exists on {data.date}: '{existing.name}'"
            )

        holiday = Holiday(
            name=data.name,
            date=data.date,
            holiday_type=data.holiday_type,
            description=data.description,
            is_active=True,
            created_by=self.current_user_id,
        )
        self.db.add(holiday)
        self.db.commit()
        self.db.refresh(holiday)

        AuditService.log(
            self.db, "holiday", holiday.id, "CREATE",
            performed_by=self.current_user_id,
            new_value={
                "name": holiday.name,
                "date": str(holiday.date),
                "holiday_type": holiday.holiday_type,
            },
        )

        RecalculationEngine.trigger(holiday.id, "CREATE", self.db)

        return HolidayResponse.model_validate(holiday)

    def update(self, id: uuid.UUID, data: HolidayUpdate) -> HolidayResponse:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")

        old_values = {
            "name": holiday.name,
            "date": str(holiday.date),
            "holiday_type": holiday.holiday_type,
            "is_active": holiday.is_active,
        }

        update_data = data.model_dump(exclude_unset=True)

        if "date" in update_data and update_data["date"] != holiday.date:
            existing = self.db.scalar(
                select(Holiday).where(
                    Holiday.date == update_data["date"],
                    Holiday.id != id,
                )
            )
            if existing:
                raise ValueError(
                    f"A holiday already exists on {update_data['date']}: '{existing.name}'"
                )

        for field, value in update_data.items():
            setattr(holiday, field, value)

        holiday.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(holiday)

        new_values = {
            "name": holiday.name,
            "date": str(holiday.date),
            "holiday_type": holiday.holiday_type,
            "is_active": holiday.is_active,
        }

        AuditService.log(
            self.db, "holiday", holiday.id, "UPDATE",
            performed_by=self.current_user_id,
            old_value=old_values,
            new_value=new_values,
        )

        if "date" in update_data or "is_active" in update_data:
            RecalculationEngine.trigger(holiday.id, "UPDATE", self.db)

        return HolidayResponse.model_validate(holiday)

    def delete(self, id: uuid.UUID) -> None:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")

        old_values = {
            "name": holiday.name,
            "date": str(holiday.date),
        }

        holiday.is_active = False
        holiday.updated_by = self.current_user_id
        self.db.commit()

        AuditService.log(
            self.db, "holiday", holiday.id, "DELETE",
            performed_by=self.current_user_id,
            old_value=old_values,
        )

        RecalculationEngine.trigger(holiday.id, "DELETE", self.db)

    def toggle_active(self, id: uuid.UUID) -> HolidayResponse:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")

        holiday.is_active = not holiday.is_active
        holiday.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(holiday)

        action = "ACTIVATE" if holiday.is_active else "DEACTIVATE"
        AuditService.log(
            self.db, "holiday", holiday.id, action,
            performed_by=self.current_user_id,
            new_value={"is_active": holiday.is_active},
        )

        RecalculationEngine.trigger(holiday.id, action, self.db)

        return HolidayResponse.model_validate(holiday)

    def get_upcoming(self, days: int = 30) -> list[HolidayResponse]:
        from datetime import timedelta
        today = date.today()
        end = today + timedelta(days=days)
        stmt = (
            select(Holiday)
            .where(
                Holiday.date >= today,
                Holiday.date <= end,
                Holiday.is_active == True,
            )
            .order_by(Holiday.date)
        )
        holidays = self.db.scalars(stmt).all()
        return [HolidayResponse.model_validate(h) for h in holidays]

    def check_date(self, check_date: date) -> HolidayResponse | None:
        holiday = self.db.scalar(
            select(Holiday).where(
                Holiday.date == check_date,
                Holiday.is_active == True,
            )
        )
        if holiday:
            return HolidayResponse.model_validate(holiday)
        return None
