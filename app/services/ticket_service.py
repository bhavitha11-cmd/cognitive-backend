import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import select, func, cast, Integer
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
from app.repositories.ticket_repository import TicketRepository
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

class TicketService:
    def __init__(self, db):
        self.db = db
        self.repo = TicketRepository(db)

    def _generate_ticket_number(self) -> str:
        # Query all ticket numbers from the database
        stmt = select(Ticket.ticket_number).where(Ticket.ticket_number.like("TCK-%"))
        ticket_numbers = self.db.scalars(stmt).all()
        
        max_num = 100
        for num_str in ticket_numbers:
            try:
                parts = num_str.split("-")
                if len(parts) == 2:
                    val = int(parts[1])
                    if val > max_num:
                        max_num = val
            except ValueError:
                continue
                
        next_num = max_num + 1
        return f"TCK-{next_num}"

    def raise_ticket(self, raised_by_id: uuid.UUID, data: dict, attachments_data: list[dict] = None) -> Ticket:
        # 1. Validate Category, Type, Priority exist and are active
        category = self.repo.get_category_by_id(data["category_id"])
        if not category or not category.is_active:
            raise ValueError("Invalid or inactive Ticket Category")

        ticket_type = self.repo.get_type_by_id(data["ticket_type_id"])
        if not ticket_type or not ticket_type.is_active or ticket_type.category_id != category.id:
            raise ValueError("Invalid or inactive Ticket Type")

        priority = self.repo.get_priority_by_id(data["priority_id"])
        if not priority or not priority.is_active:
            raise ValueError("Invalid or inactive Ticket Priority")

        # 2. Get initial status "Open"
        open_status = self.repo.get_status_by_name("Open")
        if not open_status:
            # Fallback to any active status named "Open" or first active status
            all_statuses = self.repo.get_all_statuses(is_active=True)
            if not all_statuses:
                raise ValueError("No active Ticket Statuses configured in the system")
            open_status = next((s for s in all_statuses if s.name.lower() == "open"), all_statuses[0])

        # 3. Create Ticket object
        ticket_num = self._generate_ticket_number()
        ticket = Ticket(
            id=uuid.uuid4(),
            ticket_number=ticket_num,
            category_id=category.id,
            ticket_type_id=ticket_type.id,
            subject=data["subject"],
            description=data["description"],
            priority_id=priority.id,
            status_id=open_status.id,
            raised_by_id=raised_by_id
        )
        created_ticket = self.repo.create_ticket(ticket)

        # 4. Save Attachments
        if attachments_data:
            for attach in attachments_data:
                self.repo.add_attachment(
                    ticket_id=created_ticket.id,
                    filename=attach["filename"],
                    file_url=attach["file_url"],
                    uploaded_by_id=raised_by_id
                )

        # 5. Create History audit record
        self.repo.add_history(
            ticket_id=created_ticket.id,
            action="Ticket Created",
            performed_by_id=raised_by_id,
            field_name=None,
            previous_value=None,
            new_value=None
        )

        # Refresh ticket to load relationships
        self.db.refresh(created_ticket)

        # 6. Send email notification to all handlers for the category
        self._notify_handlers(created_ticket)

        return created_ticket

    def _notify_handlers(self, ticket: Ticket) -> None:
        # Get category handlers
        handlers = self.repo.get_handlers_by_category(ticket.category_id)
        if not handlers:
            logger.warning(f"No handlers configured for ticket category '{ticket.category.name}'. Skipping email notification.")
            return

        # Fetch active configuration and send emails
        raised_by_emp = self.db.get(Employee, ticket.raised_by_id)
        raised_by_name = f"{raised_by_emp.first_name} {raised_by_emp.last_name}" if raised_by_emp else "Unknown Employee"
        raised_by_email = (raised_by_emp.official_email or raised_by_emp.email) if raised_by_emp else "unknown@cognitive.com"

        subject = f"Support Ticket raised: {ticket.ticket_number} - {ticket.subject}"
        
        # Build beautiful HTML content
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff;">
                    <h2 style="color: #206bc4; margin-top: 0;">New Support Ticket Raised</h2>
                    <p>Hello Support Handler,</p>
                    <p>A new support ticket has been raised in the <strong>{ticket.category.name}</strong> category.</p>
                    <hr style="border: 0; border-top: 1px solid #eeeeee; margin: 20px 0;" />
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold; width: 150px;">Ticket Number:</td>
                            <td style="padding: 6px 0;">{ticket.ticket_number}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold;">Category:</td>
                            <td style="padding: 6px 0;">{ticket.category.name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold;">Ticket Type:</td>
                            <td style="padding: 6px 0;">{ticket.ticket_type.name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold;">Priority:</td>
                            <td style="padding: 6px 0;">
                                <span style="background-color: #f1f5f9; padding: 2px 8px; border-radius: 4px; font-size: 0.9em;">
                                    {ticket.priority.name}
                                </span>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold;">Subject:</td>
                            <td style="padding: 6px 0; font-weight: {ticket.subject}">{ticket.subject}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold; vertical-align: top;">Description:</td>
                            <td style="padding: 6px 0; white-space: pre-wrap;">{ticket.description}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold;">Raised By:</td>
                            <td style="padding: 6px 0;">{raised_by_name} ({raised_by_email})</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold;">Created At:</td>
                            <td style="padding: 6px 0;">{ticket.created_at.strftime("%Y-%m-%d %H:%M:%S") if ticket.created_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td>
                        </tr>
                    </table>
                    <hr style="border: 0; border-top: 1px solid #eeeeee; margin: 20px 0;" />
                    <p style="font-size: 0.9em; color: #666666;">
                        Please log in to the Cognitive ERP Support Panel to view and update this ticket.
                    </p>
                </div>
            </body>
        </html>
        """

        for h in handlers:
            handler_emp = self.db.get(Employee, h.employee_id)
            if handler_emp and handler_emp.is_active:
                to_email = handler_emp.official_email or handler_emp.email
                if to_email:
                    logger.info(f"Sending ticket notification email to handler: {to_email}")
                    EmailService.send_email_with_active_config(
                        db=self.db,
                        to_email=to_email,
                        subject=subject,
                        html_content=html_content
                    )

    def get_my_tickets(self, raised_by_id: uuid.UUID) -> list[Ticket]:
        return self.repo.get_tickets_by_raised_by(raised_by_id)

    def get_category_tickets(self, employee_id: uuid.UUID, is_super_admin: bool = False) -> list[Ticket]:
        if is_super_admin:
            return self.repo.get_all_tickets()
        
        # Get categories handled by this employee
        handlers = self.repo.get_handlers_by_employee(employee_id)
        category_ids = [h.category_id for h in handlers]
        return self.repo.get_tickets_by_categories(category_ids)

    def is_employee_handler(self, employee_id: uuid.UUID) -> bool:
        handlers = self.repo.get_handlers_by_employee(employee_id)
        return len(handlers) > 0

    def get_ticket_details(self, ticket_id: uuid.UUID, employee_id: uuid.UUID, is_super_admin: bool = False) -> Ticket:
        ticket = self.repo.get_ticket_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        # Access check: Must be raised_by, a configured handler for the ticket category, or admin
        if is_super_admin or ticket.raised_by_id == employee_id:
            return ticket

        # Check if user is a handler for this category
        handler = self.repo.get_handler_by_category_and_employee(ticket.category_id, employee_id)
        if not handler:
            raise ValueError("Access Denied: You do not have permission to view this ticket")

        return ticket

    def update_ticket_status(self, ticket_id: uuid.UUID, performed_by_id: uuid.UUID, new_status_id: uuid.UUID, is_super_admin: bool = False) -> Ticket:
        ticket = self.repo.get_ticket_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        # Access check: Must be a configured handler for the category or admin
        if not is_super_admin:
            handler = self.repo.get_handler_by_category_and_employee(ticket.category_id, performed_by_id)
            if not handler:
                raise ValueError("Access Denied: Only support handlers can update ticket status")

        new_status = self.repo.get_status_by_id(new_status_id)
        if not new_status or not new_status.is_active:
            raise ValueError("Invalid or inactive Ticket Status")

        if ticket.status_id == new_status.id:
            return ticket  # No change

        old_status_name = ticket.status.name
        new_status_name = new_status.name

        # Update status
        ticket.status_id = new_status.id
        ticket.updated_at = datetime.now(timezone.utc)
        self.repo.save_ticket()

        # Audit History Status Changed
        self.repo.add_history(
            ticket_id=ticket.id,
            action="Status Changed",
            performed_by_id=performed_by_id,
            field_name="status",
            previous_value=old_status_name,
            new_value=new_status_name
        )

        # Audit History Ticket Closed (if closed/resolved)
        if new_status_name.lower() in ("closed", "resolved"):
            self.repo.add_history(
                ticket_id=ticket.id,
                action="Ticket Closed",
                performed_by_id=performed_by_id,
                field_name="status",
                previous_value=old_status_name,
                new_value=new_status_name
            )

        self.db.refresh(ticket)
        return ticket

    def add_comment(self, ticket_id: uuid.UUID, commented_by_id: uuid.UUID, comment_text: str, is_super_admin: bool = False) -> TicketComment:
        ticket = self.repo.get_ticket_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        # Access check: Must be raised_by, a configured handler, or admin
        if not is_super_admin and ticket.raised_by_id != commented_by_id:
            handler = self.repo.get_handler_by_category_and_employee(ticket.category_id, commented_by_id)
            if not handler:
                raise ValueError("Access Denied: You do not have permission to comment on this ticket")

        # Save Comment
        comment = self.repo.add_comment(ticket.id, commented_by_id, comment_text)

        # Audit History Comment Added
        self.repo.add_history(
            ticket_id=ticket.id,
            action="Comment Added",
            performed_by_id=commented_by_id,
            field_name=None,
            previous_value=None,
            new_value=None
        )

        # Update ticket last updated timestamp
        ticket.updated_at = datetime.now(timezone.utc)
        self.repo.save_ticket()

        return comment
