from __future__ import annotations
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base
from app.models.employee import Employee
from app.models.role import Role
from app.models.ticket_category import TicketCategory
from app.models.ticket_type import TicketType
from app.models.ticket_priority import TicketPriority
from app.models.ticket_status import TicketStatus
from app.models.ticket_category_handler import TicketCategoryHandler
from app.models.ticket import Ticket
from app.models.ticket_attachment import TicketAttachment
from app.models.ticket_comment import TicketComment
from app.models.ticket_history import TicketHistory
from app.services.ticket_service import TicketService

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

@pytest.fixture(name="engine")
def fixture_engine():
    return create_engine("sqlite:///:memory:")

@pytest.fixture(name="db_session")
def fixture_db_session(engine):
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="seed_data")
def fixture_seed_data(db_session):
    # Create an employee
    emp = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-100",
        first_name="Test",
        last_name="User",
        email="test@cognitive.com",
        username="testuser",
        password_hash="hash",
        account_status="ACTIVE",
        is_active=True,
        gender="MALE",
    )
    db_session.add(emp)

    # Create handler employee
    handler_emp = Employee(
        id=uuid.uuid4(),
        employee_code="EMP-101",
        first_name="Support",
        last_name="Handler",
        email="support@cognitive.com",
        username="support",
        password_hash="hash",
        account_status="ACTIVE",
        is_active=True,
        gender="FEMALE",
    )
    db_session.add(handler_emp)

    # Ticket Configs
    cat_it = TicketCategory(id=uuid.UUID("11111111-1111-1111-1111-11111111111a"), name="IT", is_active=True)
    cat_stat = TicketCategory(id=uuid.UUID("22222222-2222-2222-2222-22222222222b"), name="Stationery", is_active=True)
    db_session.add_all([cat_it, cat_stat])

    type_laptop = TicketType(id=uuid.uuid4(), category_id=cat_it.id, name="Laptop Issue", is_active=True)
    type_pen = TicketType(id=uuid.uuid4(), category_id=cat_stat.id, name="Pen Request", is_active=True)
    db_session.add_all([type_laptop, type_pen])

    prio_high = TicketPriority(id=uuid.uuid4(), name="High", is_active=True)
    prio_low = TicketPriority(id=uuid.uuid4(), name="Low", is_active=True)
    db_session.add_all([prio_high, prio_low])

    status_open = TicketStatus(id=uuid.uuid4(), name="Open", is_active=True)
    status_ip = TicketStatus(id=uuid.uuid4(), name="In Progress", is_active=True)
    status_closed = TicketStatus(id=uuid.uuid4(), name="Closed", is_active=True)
    db_session.add_all([status_open, status_ip, status_closed])

    db_session.commit()

    # Handlers config
    handler = TicketCategoryHandler(id=uuid.uuid4(), category_id=cat_it.id, employee_id=handler_emp.id)
    db_session.add(handler)
    db_session.commit()

    return {
        "employee_id": emp.id,
        "handler_id": handler_emp.id,
        "category_it_id": cat_it.id,
        "category_stat_id": cat_stat.id,
        "type_laptop_id": type_laptop.id,
        "type_pen_id": type_pen.id,
        "prio_high_id": prio_high.id,
        "prio_low_id": prio_low.id,
        "status_open_id": status_open.id,
        "status_ip_id": status_ip.id,
        "status_closed_id": status_closed.id,
    }

@patch("app.services.ticket_service.EmailService.send_email_with_active_config")
def test_raise_ticket_success(mock_send_email, db_session, seed_data):
    service = TicketService(db_session)
    data = {
        "category_id": seed_data["category_it_id"],
        "ticket_type_id": seed_data["type_laptop_id"],
        "subject": "Laptop won't boot",
        "description": "Black screen on power press",
        "priority_id": seed_data["prio_high_id"]
    }
    attachments = [
        {"filename": "screenshot.png", "file_url": "/api/v1/tickets/document/abc.png"}
    ]

    ticket = service.raise_ticket(raised_by_id=seed_data["employee_id"], data=data, attachments_data=attachments)

    assert ticket.ticket_number == "TCK-101"
    assert ticket.subject == "Laptop won't boot"
    assert ticket.status.name == "Open"
    assert len(ticket.attachments) == 1
    assert ticket.attachments[0].filename == "screenshot.png"

    # Verify history
    assert len(ticket.history) == 1
    assert ticket.history[0].action == "Ticket Created"

    # Email notification check
    assert mock_send_email.call_count == 1

def test_raise_ticket_invalid_category(db_session, seed_data):
    service = TicketService(db_session)
    data = {
        "category_id": uuid.uuid4(),  # Random ID
        "ticket_type_id": seed_data["type_laptop_id"],
        "subject": "Bad category",
        "description": "Test",
        "priority_id": seed_data["prio_high_id"]
    }
    with pytest.raises(ValueError, match="Invalid or inactive Ticket Category"):
        service.raise_ticket(raised_by_id=seed_data["employee_id"], data=data)

def test_raise_ticket_type_category_mismatch(db_session, seed_data):
    service = TicketService(db_session)
    data = {
        "category_id": seed_data["category_stat_id"], # Stationery category
        "ticket_type_id": seed_data["type_laptop_id"], # But IT type
        "subject": "Mismatch",
        "description": "Test",
        "priority_id": seed_data["prio_high_id"]
    }
    with pytest.raises(ValueError, match="Invalid or inactive Ticket Type"):
        service.raise_ticket(raised_by_id=seed_data["employee_id"], data=data)

def test_update_ticket_status(db_session, seed_data):
    service = TicketService(db_session)
    
    # 1. Create a ticket
    ticket = Ticket(
        id=uuid.uuid4(),
        ticket_number="TCK-101",
        category_id=seed_data["category_it_id"],
        ticket_type_id=seed_data["type_laptop_id"],
        subject="Laptop issue",
        description="Text",
        priority_id=seed_data["prio_high_id"],
        status_id=seed_data["status_open_id"],
        raised_by_id=seed_data["employee_id"]
    )
    db_session.add(ticket)
    db_session.commit()

    # 2. Update to In Progress (performed by handler)
    updated = service.update_ticket_status(
        ticket_id=ticket.id,
        performed_by_id=seed_data["handler_id"],
        new_status_id=seed_data["status_ip_id"]
    )
    assert updated.status_id == seed_data["status_ip_id"]
    assert len(updated.history) == 1
    assert updated.history[0].action == "Status Changed"
    assert updated.history[0].field_name == "status"
    assert updated.history[0].previous_value == "Open"
    assert updated.history[0].new_value == "In Progress"

    # 3. Close the ticket
    closed = service.update_ticket_status(
        ticket_id=ticket.id,
        performed_by_id=seed_data["handler_id"],
        new_status_id=seed_data["status_closed_id"]
    )
    assert closed.status_id == seed_data["status_closed_id"]
    # Should have two history records now: "Status Changed" and "Ticket Closed"
    history_actions = [h.action for h in closed.history]
    assert "Ticket Closed" in history_actions

def test_add_comment(db_session, seed_data):
    service = TicketService(db_session)
    ticket = Ticket(
        id=uuid.uuid4(),
        ticket_number="TCK-102",
        category_id=seed_data["category_it_id"],
        ticket_type_id=seed_data["type_laptop_id"],
        subject="Laptop issue",
        description="Text",
        priority_id=seed_data["prio_high_id"],
        status_id=seed_data["status_open_id"],
        raised_by_id=seed_data["employee_id"]
    )
    db_session.add(ticket)
    db_session.commit()

    # Comment by employee
    comment = service.add_comment(
        ticket_id=ticket.id,
        commented_by_id=seed_data["employee_id"],
        comment_text="I tried rebooting, still black."
    )
    assert comment.comment == "I tried rebooting, still black."
    assert comment.commented_by_id == seed_data["employee_id"]

    db_session.refresh(ticket)
    assert len(ticket.comments) == 1
    assert len(ticket.history) == 1
    assert ticket.history[0].action == "Comment Added"

def test_get_category_tickets_isolation(db_session, seed_data):
    service = TicketService(db_session)
    
    # Ticket in IT (seed_data handler handles IT)
    ticket_it = Ticket(
        id=uuid.uuid4(),
        ticket_number="TCK-201",
        category_id=seed_data["category_it_id"],
        ticket_type_id=seed_data["type_laptop_id"],
        subject="IT Help",
        description="Broken laptop",
        priority_id=seed_data["prio_high_id"],
        status_id=seed_data["status_open_id"],
        raised_by_id=seed_data["employee_id"]
    )
    # Ticket in Stationery (seed_data handler NOT handler for Stationery)
    ticket_stat = Ticket(
        id=uuid.uuid4(),
        ticket_number="TCK-202",
        category_id=seed_data["category_stat_id"],
        ticket_type_id=seed_data["type_pen_id"],
        subject="Stationery request",
        description="Need pen",
        priority_id=seed_data["prio_low_id"],
        status_id=seed_data["status_open_id"],
        raised_by_id=seed_data["employee_id"]
    )
    db_session.add_all([ticket_it, ticket_stat])
    db_session.commit()

    # Get tickets for handler (should only return IT ticket)
    tickets = service.get_category_tickets(employee_id=seed_data["handler_id"])
    assert len(tickets) == 1
    assert tickets[0].ticket_number == "TCK-201"

    # Get tickets for admin (should return both tickets)
    admin_tickets = service.get_category_tickets(employee_id=seed_data["handler_id"], is_super_admin=True)
    assert len(admin_tickets) == 2
