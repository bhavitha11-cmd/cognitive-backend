import uuid
from sqlalchemy import select, or_
from app.models.ticket_category import TicketCategory
from app.models.ticket_type import TicketType
from app.models.ticket_priority import TicketPriority
from app.models.ticket_status import TicketStatus
from app.models.ticket_category_handler import TicketCategoryHandler
from app.models.ticket import Ticket
from app.models.ticket_attachment import TicketAttachment
from app.models.ticket_comment import TicketComment
from app.models.ticket_history import TicketHistory
from app.models.employee import Employee
from app.repositories.base import BaseRepository

class TicketRepository(BaseRepository):
    # Categories
    def get_category_by_id(self, id: uuid.UUID) -> TicketCategory | None:
        return self.db.get(TicketCategory, id)

    def get_category_by_name(self, name: str) -> TicketCategory | None:
        return self.db.scalar(select(TicketCategory).where(TicketCategory.name.ilike(name)))

    def get_all_categories(self, is_active: bool | None = None) -> list[TicketCategory]:
        stmt = select(TicketCategory)
        if is_active is not None:
            stmt = stmt.where(TicketCategory.is_active == is_active)
        stmt = stmt.order_by(TicketCategory.name)
        return list(self.db.scalars(stmt).all())

    def create_category(self, data: dict) -> TicketCategory:
        category = TicketCategory(**data)
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    def update_category(self, category: TicketCategory, data: dict) -> TicketCategory:
        for k, v in data.items():
            setattr(category, k, v)
        self.db.commit()
        self.db.refresh(category)
        return category

    def delete_category(self, category: TicketCategory) -> None:
        self.db.delete(category)
        self.db.commit()

    # Types
    def get_type_by_id(self, id: uuid.UUID) -> TicketType | None:
        return self.db.get(TicketType, id)

    def get_all_types(self, category_id: uuid.UUID | None = None, is_active: bool | None = None) -> list[TicketType]:
        stmt = select(TicketType)
        if category_id is not None:
            stmt = stmt.where(TicketType.category_id == category_id)
        if is_active is not None:
            stmt = stmt.where(TicketType.is_active == is_active)
        stmt = stmt.order_by(TicketType.name)
        return list(self.db.scalars(stmt).all())

    def create_type(self, data: dict) -> TicketType:
        ttype = TicketType(**data)
        self.db.add(ttype)
        self.db.commit()
        self.db.refresh(ttype)
        return ttype

    def update_type(self, ttype: TicketType, data: dict) -> TicketType:
        for k, v in data.items():
            setattr(ttype, k, v)
        self.db.commit()
        self.db.refresh(ttype)
        return ttype

    def delete_type(self, ttype: TicketType) -> None:
        self.db.delete(ttype)
        self.db.commit()

    # Priorities
    def get_priority_by_id(self, id: uuid.UUID) -> TicketPriority | None:
        return self.db.get(TicketPriority, id)

    def get_priority_by_name(self, name: str) -> TicketPriority | None:
        return self.db.scalar(select(TicketPriority).where(TicketPriority.name.ilike(name)))

    def get_all_priorities(self, is_active: bool | None = None) -> list[TicketPriority]:
        stmt = select(TicketPriority)
        if is_active is not None:
            stmt = stmt.where(TicketPriority.is_active == is_active)
        stmt = stmt.order_by(TicketPriority.name)
        return list(self.db.scalars(stmt).all())

    def create_priority(self, data: dict) -> TicketPriority:
        priority = TicketPriority(**data)
        self.db.add(priority)
        self.db.commit()
        self.db.refresh(priority)
        return priority

    def update_priority(self, priority: TicketPriority, data: dict) -> TicketPriority:
        for k, v in data.items():
            setattr(priority, k, v)
        self.db.commit()
        self.db.refresh(priority)
        return priority

    def delete_priority(self, priority: TicketPriority) -> None:
        self.db.delete(priority)
        self.db.commit()

    # Statuses
    def get_status_by_id(self, id: uuid.UUID) -> TicketStatus | None:
        return self.db.get(TicketStatus, id)

    def get_status_by_name(self, name: str) -> TicketStatus | None:
        return self.db.scalar(select(TicketStatus).where(TicketStatus.name.ilike(name)))

    def get_all_statuses(self, is_active: bool | None = None) -> list[TicketStatus]:
        stmt = select(TicketStatus)
        if is_active is not None:
            stmt = stmt.where(TicketStatus.is_active == is_active)
        stmt = stmt.order_by(TicketStatus.name)
        return list(self.db.scalars(stmt).all())

    def create_status(self, data: dict) -> TicketStatus:
        status = TicketStatus(**data)
        self.db.add(status)
        self.db.commit()
        self.db.refresh(status)
        return status

    def update_status(self, status: TicketStatus, data: dict) -> TicketStatus:
        for k, v in data.items():
            setattr(status, k, v)
        self.db.commit()
        self.db.refresh(status)
        return status

    def delete_status(self, status: TicketStatus) -> None:
        self.db.delete(status)
        self.db.commit()

    # Category Handlers
    def get_handler_by_id(self, id: uuid.UUID) -> TicketCategoryHandler | None:
        return self.db.get(TicketCategoryHandler, id)

    def get_handlers_by_category(self, category_id: uuid.UUID, is_active: bool | None = None) -> list[TicketCategoryHandler]:
        stmt = select(TicketCategoryHandler).where(TicketCategoryHandler.category_id == category_id)
        if is_active is not None:
            stmt = stmt.where(TicketCategoryHandler.is_active == is_active)
        return list(self.db.scalars(stmt).all())

    def get_handlers_by_employee(self, employee_id: uuid.UUID, is_active: bool | None = None) -> list[TicketCategoryHandler]:
        stmt = select(TicketCategoryHandler).where(TicketCategoryHandler.employee_id == employee_id)
        if is_active is not None:
            stmt = stmt.where(TicketCategoryHandler.is_active == is_active)
        return list(self.db.scalars(stmt).all())

    def get_handler_by_category_and_employee(self, category_id: uuid.UUID, employee_id: uuid.UUID, is_active: bool | None = None) -> TicketCategoryHandler | None:
        stmt = select(TicketCategoryHandler).where(
            TicketCategoryHandler.category_id == category_id,
            TicketCategoryHandler.employee_id == employee_id
        )
        if is_active is not None:
            stmt = stmt.where(TicketCategoryHandler.is_active == is_active)
        return self.db.scalar(stmt)

    def get_all_handlers(self) -> list[TicketCategoryHandler]:
        return list(self.db.scalars(select(TicketCategoryHandler)).all())

    def create_handler(self, category_id: uuid.UUID, employee_id: uuid.UUID) -> TicketCategoryHandler:
        handler = TicketCategoryHandler(category_id=category_id, employee_id=employee_id)
        self.db.add(handler)
        self.db.commit()
        self.db.refresh(handler)
        return handler

    def delete_handler(self, handler: TicketCategoryHandler) -> None:
        self.db.delete(handler)
        self.db.commit()

    # Tickets CRUD
    def get_ticket_by_id(self, id: uuid.UUID) -> Ticket | None:
        return self.db.get(Ticket, id)

    def get_tickets_by_raised_by(self, raised_by_id: uuid.UUID) -> list[Ticket]:
        stmt = select(Ticket).where(Ticket.raised_by_id == raised_by_id).order_by(Ticket.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get_tickets_by_categories(self, category_ids: list[uuid.UUID]) -> list[Ticket]:
        if not category_ids:
            return []
        stmt = select(Ticket).where(Ticket.category_id.in_(category_ids)).order_by(Ticket.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get_all_tickets(self) -> list[Ticket]:
        stmt = select(Ticket).order_by(Ticket.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def create_ticket(self, ticket: Ticket) -> Ticket:
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def save_ticket(self) -> None:
        self.db.commit()

    # Comments
    def add_comment(self, ticket_id: uuid.UUID, commented_by_id: uuid.UUID, comment_text: str) -> TicketComment:
        comment = TicketComment(ticket_id=ticket_id, commented_by_id=commented_by_id, comment=comment_text)
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    # History
    def add_history(self, ticket_id: uuid.UUID, action: str, performed_by_id: uuid.UUID, field_name: str | None = None, previous_value: str | None = None, new_value: str | None = None) -> TicketHistory:
        history = TicketHistory(
            ticket_id=ticket_id,
            action=action,
            field_name=field_name,
            previous_value=previous_value,
            new_value=new_value,
            performed_by_id=performed_by_id
        )
        self.db.add(history)
        self.db.commit()
        self.db.refresh(history)
        return history

    # Attachments
    def add_attachment(self, ticket_id: uuid.UUID, filename: str, file_url: str, uploaded_by_id: uuid.UUID | None) -> TicketAttachment:
        attachment = TicketAttachment(
            ticket_id=ticket_id,
            filename=filename,
            file_url=file_url,
            uploaded_by_id=uploaded_by_id
        )
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)
        return attachment
