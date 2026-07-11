from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select, delete
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.leave_balance import LeaveBalance
from app.models.leave_request import LeaveRequest
from app.models.leave_type import LeaveType
from app.schemas.leave import (
    LeaveApprovalRequest,
    LeaveBalanceResponse,
    LeaveRequestCreate,
    LeaveRequestResponse,
    LeaveRequestUpdate,
    LeaveTypeCreate,
    LeaveTypeResponse,
    LeaveTypeUpdate,
)
from app.services.audit_service import AuditService


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _build_leave_type_response(lt: LeaveType) -> LeaveTypeResponse:
    return LeaveTypeResponse(
        id=lt.id,
        code=lt.code,
        name=lt.name,
        days_per_year=float(lt.days_per_year),
        max_carry_forward_days=float(lt.max_carry_forward_days),
        is_paid=lt.is_paid,
        is_carry_forward=lt.is_carry_forward,
        requires_approval=lt.requires_approval,
        requires_document=lt.requires_document,
        is_active=lt.is_active,
        color=lt.color,
        description=lt.description,
        created_at=lt.created_at,
    )


def _build_balance_response(
    balance: LeaveBalance,
    employee: Employee | None = None,
    leave_type: LeaveType | None = None,
) -> LeaveBalanceResponse:
    emp = employee or balance.employee
    lt = leave_type or balance.leave_type

    total_allowed = float(balance.total_allowed)
    used = float(balance.used)
    carried_forward = float(balance.carried_forward)
    remaining = total_allowed + carried_forward - used

    emp_name: str | None = None
    if emp:
        emp_name = f"{emp.first_name} {emp.last_name}"

    return LeaveBalanceResponse(
        id=balance.id,
        employee_id=balance.employee_id,
        employee_name=emp_name,
        leave_type_id=balance.leave_type_id,
        leave_type_name=lt.name if lt else None,
        leave_type_code=lt.code if lt else None,
        year=balance.year,
        total_allowed=total_allowed,
        used=used,
        carried_forward=carried_forward,
        remaining=remaining,
    )


def _build_request_response(req: LeaveRequest, db: Session | None = None) -> LeaveRequestResponse:
    emp = req.employee
    lt = req.leave_type

    emp_name: str | None = None
    emp_code: str | None = None
    if emp:
        emp_name = f"{emp.first_name} {emp.last_name}"
        emp_code = emp.employee_code

    steps_data = []
    if db:
        from app.models.approval import ApprovalInstance
        from app.models.role import Role
        from app.models.employee import Employee
        instances = db.scalars(
            select(ApprovalInstance)
            .where(
                ApprovalInstance.target_id == req.id,
                ApprovalInstance.module_type == "LEAVE"
            )
            .order_by(ApprovalInstance.level)
        ).all()
        for inst in instances:
            app_role = db.get(Role, inst.approver_role_id)
            assigned_emp = db.get(Employee, inst.assigned_approver_id) if inst.assigned_approver_id else None
            actioned_emp = db.get(Employee, inst.actioned_by_id) if inst.actioned_by_id else None
            steps_data.append({
                "id": str(inst.id),
                "level": inst.level,
                "status": inst.status,
                "approver_role_name": app_role.name if app_role else None,
                "assigned_approver_name": f"{assigned_emp.first_name} {assigned_emp.last_name}" if assigned_emp else None,
                "actioned_by_name": f"{actioned_emp.first_name} {actioned_emp.last_name}" if actioned_emp else None,
                "comments": inst.comments,
            })

    return LeaveRequestResponse(
        id=req.id,
        employee_id=req.employee_id,
        employee_name=emp_name,
        employee_code=emp_code,
        leave_type_id=req.leave_type_id,
        leave_type_name=lt.name if lt else None,
        leave_type_code=lt.code if lt else None,
        from_date=req.from_date,
        to_date=req.to_date,
        total_days=float(req.total_days),
        reason=req.reason,
        status=req.status,
        applied_at=req.applied_at,
        approved_by=req.approved_by,
        approved_at=req.approved_at,
        rejection_reason=req.rejection_reason,
        hr_notes=req.hr_notes,
        approval_steps=steps_data if db else None,
        document_url=req.document_url,
        is_half_day=req.is_half_day,
        half_day_session=req.half_day_session,
    )


class LeaveService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def _count_working_days(self, start_date: date, end_date: date, db=None) -> int:
        """Count working days between start and end date (inclusive).

        Delegates to the shared WorkingDayEngine so that holidays and the org
        work_days configuration are respected (not just Sat/Sun).
        """
        from app.services.working_day_engine import WorkingDayEngine

        return WorkingDayEngine.count_working_days(start_date, end_date, db or self.db)

    def _create_on_leave_attendance(self, req: LeaveRequest, actioned_by: UUID | None = None) -> None:
        from app.models.attendance import Attendance
        from app.services.working_day_engine import WorkingDayEngine

        current = req.from_date
        while current <= req.to_date:
            if WorkingDayEngine.is_working_day(current, self.db):
                existing = self.db.scalars(
                    select(Attendance).where(
                        Attendance.employee_id == req.employee_id,
                        Attendance.date == current,
                    )
                ).first()

                # Determine notes and status
                status_str = "ON_LEAVE"
                notes_prefix = "Approved leave request"
                if req.is_half_day:
                    session_name = "First Half" if req.half_day_session == "FIRST_HALF" else "Second Half"
                    notes_prefix = f"Approved half-day leave ({session_name})"

                if existing:
                    if existing.notes and "Approved half-day leave" in existing.notes:
                        existing.notes = f"{existing.notes} | {notes_prefix}: {req.reason or 'No reason provided'}"
                    else:
                        existing.notes = f"{notes_prefix}: {req.reason or 'No reason provided'}"
                    existing.status = status_str
                    existing.marked_by = actioned_by or self.current_user_id
                    self.db.add(existing)
                else:
                    new_record = Attendance(
                        employee_id=req.employee_id,
                        date=current,
                        status=status_str,
                        marked_by=actioned_by or self.current_user_id,
                        notes=f"{notes_prefix}: {req.reason or 'No reason provided'}",
                    )
                    self.db.add(new_record)
            current += timedelta(days=1)
        self.db.flush()

    def _delete_on_leave_attendance(self, req: LeaveRequest) -> None:
        from app.models.attendance import Attendance

        self.db.execute(
            delete(Attendance).where(
                Attendance.employee_id == req.employee_id,
                Attendance.date.between(req.from_date, req.to_date),
                Attendance.status == "ON_LEAVE",
            )
        )
        self.db.flush()

    # ── Leave Types ────────────────────────────────────────────────────────────

    def get_all_leave_types(self, include_inactive: bool = False) -> list[LeaveTypeResponse]:
        stmt = select(LeaveType)
        if not include_inactive:
            stmt = stmt.where(LeaveType.is_active.is_(True))
        stmt = stmt.order_by(LeaveType.name)
        leave_types = self.db.scalars(stmt).all()
        return [_build_leave_type_response(lt) for lt in leave_types]

    def get_leave_type(self, id: UUID) -> LeaveTypeResponse:
        lt = self.db.get(LeaveType, id)
        if not lt:
            raise ValueError(f"Leave type with id {id} not found")
        return _build_leave_type_response(lt)

    def create_leave_type(self, data: LeaveTypeCreate) -> LeaveTypeResponse:
        existing = self.db.scalars(
            select(LeaveType).where(LeaveType.code.ilike(data.code))
        ).first()
        if existing:
            raise ValueError(f"Leave type with code '{data.code}' already exists")

        lt = LeaveType(
            code=data.code.upper(),
            name=data.name,
            days_per_year=data.days_per_year,
            is_paid=data.is_paid,
            is_carry_forward=data.is_carry_forward,
            max_carry_forward_days=data.max_carry_forward_days,
            requires_approval=data.requires_approval,
            requires_document=data.requires_document,
            color=data.color,
            description=data.description,
        )
        try:
            self.db.add(lt)
            self.db.flush()  # assign lt.id before audit, still inside the txn
            AuditService.log(
                self.db,
                "leave_type",
                lt.id,
                "CREATE",
                performed_by=self.current_user_id,
                new_value={"code": lt.code, "name": lt.name},
            )
            self.db.commit()
            self.db.refresh(lt)
            return _build_leave_type_response(lt)
        except Exception:
            self.db.rollback()
            raise

    def update_leave_type(self, id: UUID, data: LeaveTypeUpdate) -> LeaveTypeResponse:
        lt = self.db.get(LeaveType, id)
        if not lt:
            raise ValueError(f"Leave type with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        if "code" in update_data:
            new_code = update_data["code"].upper()
            update_data["code"] = new_code
            conflict = self.db.scalars(
                select(LeaveType).where(
                    LeaveType.code.ilike(new_code),
                    LeaveType.id != id,
                )
            ).first()
            if conflict:
                raise ValueError(f"Leave type with code '{new_code}' already exists")

        old_values = {k: getattr(lt, k, None) for k in update_data}
        try:
            for key, value in update_data.items():
                setattr(lt, key, value)
            AuditService.log(
                self.db,
                "leave_type",
                id,
                "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values,
                new_value=update_data,
            )
            self.db.commit()
            self.db.refresh(lt)
            return _build_leave_type_response(lt)
        except Exception:
            self.db.rollback()
            raise

    def delete_leave_type(self, id: UUID) -> None:
        lt = self.db.get(LeaveType, id)
        if not lt:
            raise ValueError(f"Leave type with id {id} not found")

        pending_count = self.db.scalar(
            select(func.count(LeaveRequest.id)).where(
                LeaveRequest.leave_type_id == id,
                LeaveRequest.status == "PENDING",
            )
        ) or 0
        if pending_count:
            raise ValueError(
                f"Cannot delete leave type '{lt.name}': {pending_count} pending request(s) exist. "
                "Resolve them first."
            )

        try:
            AuditService.log(
                self.db,
                "leave_type",
                id,
                "DELETE",
                performed_by=self.current_user_id,
                old_value={"code": lt.code, "name": lt.name},
            )
            lt.is_active = False
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # ── Leave Balances ─────────────────────────────────────────────────────────

    def get_balance(
        self, employee_id: UUID, year: int | None = None
    ) -> list[LeaveBalanceResponse]:
        year = year or _current_year()
        balances = self.db.scalars(
            select(LeaveBalance)
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == year,
            )
            .order_by(LeaveBalance.leave_type_id)
        ).all()
        return [_build_balance_response(b) for b in balances]

    def initialize_balances(
        self, employee_id: UUID, year: int | None = None
    ) -> list[LeaveBalanceResponse]:
        year = year or _current_year()

        # Verify employee exists
        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError(f"Employee with id {employee_id} not found")

        active_types = self.db.scalars(
            select(LeaveType).where(LeaveType.is_active.is_(True))
        ).all()

        results: list[LeaveBalanceResponse] = []
        try:
            for lt in active_types:
                balance = self._ensure_balance_exists(employee_id, lt.id, year)

                # Set total_allowed with proration from leave type based on joining date
                days_allowed = float(lt.days_per_year)
                if employee.date_of_joining:
                    joining_year = employee.date_of_joining.year
                    if joining_year == year:
                        joining_month = employee.date_of_joining.month
                        remaining_months = 12 - joining_month + 1
                        prorated = (days_allowed * remaining_months) / 12.0
                        days_allowed = round(prorated * 2) / 2.0
                    elif joining_year > year:
                        days_allowed = 0.0
                balance.total_allowed = days_allowed

                # Carry forward from prior year if applicable
                if lt.is_carry_forward:
                    prior_balance = self.db.scalars(
                        select(LeaveBalance).where(
                            LeaveBalance.employee_id == employee_id,
                            LeaveBalance.leave_type_id == lt.id,
                            LeaveBalance.year == year - 1,
                        )
                    ).first()
                    if prior_balance:
                        prior_remaining = (
                            float(prior_balance.total_allowed)
                            + float(prior_balance.carried_forward)
                            - float(prior_balance.used)
                        )
                        carry = max(0.0, min(prior_remaining, float(lt.max_carry_forward_days)))
                        balance.carried_forward = carry
                    else:
                        balance.carried_forward = 0.0
                else:
                    balance.carried_forward = 0.0

                self.db.add(balance)

            self.db.flush()

            AuditService.log(
                self.db,
                "leave_balance",
                employee_id,
                "INITIALIZE",
                performed_by=self.current_user_id,
                new_value={"employee_id": str(employee_id), "year": year},
            )

            self.db.commit()

            # Refresh and build responses
            for lt in active_types:
                balance = self.db.scalars(
                    select(LeaveBalance).where(
                        LeaveBalance.employee_id == employee_id,
                        LeaveBalance.leave_type_id == lt.id,
                        LeaveBalance.year == year,
                    )
                ).first()
                if balance:
                    self.db.refresh(balance)
                    results.append(_build_balance_response(balance))
        except Exception:
            self.db.rollback()
            raise

        return results

    def _ensure_balance_exists(
        self, employee_id: UUID, leave_type_id: UUID, year: int
    ) -> LeaveBalance:
        balance = self.db.scalars(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == year,
            )
        ).first()
        if not balance:
            balance = LeaveBalance(
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                year=year,
                total_allowed=0,
                used=0,
                carried_forward=0,
            )
        return balance

    def _recompute_used(
        self, employee_id: UUID, leave_type_id: UUID, year: int
    ) -> None:
        total_used = self.db.scalar(
            select(func.coalesce(func.sum(LeaveRequest.total_days), 0)).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.leave_type_id == leave_type_id,
                LeaveRequest.status == "APPROVED",
                func.extract("year", LeaveRequest.from_date) == year,
            )
        ) or 0.0

        balance = self.db.scalars(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == year,
            )
        ).first()
        if balance:
            balance.used = float(total_used)
            self.db.add(balance)
            self.db.flush()  # Changed from db.commit() - callers own the transaction boundary

    # ── Leave Requests ─────────────────────────────────────────────────────────

    def get_all_requests(
        self,
        skip: int = 0,
        limit: int = 50,
        employee_id: UUID | None = None,
        status: str | None = None,
        year: int | None = None,
    ) -> tuple[list[LeaveRequestResponse], int]:
        stmt = select(LeaveRequest)

        if employee_id:
            stmt = stmt.where(LeaveRequest.employee_id == employee_id)
        if status:
            stmt = stmt.where(LeaveRequest.status == status.upper())
        if year:
            stmt = stmt.where(
                func.extract("year", LeaveRequest.from_date) == year
            )

        total = self.db.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        requests = self.db.scalars(
            stmt.order_by(LeaveRequest.applied_at.desc()).offset(skip).limit(limit)
        ).all()

        return [_build_request_response(r, self.db) for r in requests], total

    def get_my_requests(
        self,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
        year: int | None = None,
    ) -> tuple[list[LeaveRequestResponse], int]:
        return self.get_all_requests(
            skip=skip,
            limit=limit,
            employee_id=self.current_user_id,
            status=status,
            year=year,
        )

    def get_request(self, id: UUID) -> LeaveRequestResponse:
        req = self.db.get(LeaveRequest, id)
        if not req:
            raise ValueError(f"Leave request with id {id} not found")
        return _build_request_response(req, self.db)

    def apply_leave(
        self,
        data: LeaveRequestCreate,
        employee_id: UUID | None = None,
    ) -> LeaveRequestResponse:
        emp_id = employee_id or self.current_user_id
        if not emp_id:
            raise ValueError("Employee ID is required to apply for leave")

        # Verify employee exists
        employee = self.db.get(Employee, emp_id)
        if not employee:
            raise ValueError(f"Employee with id {emp_id} not found")

        # Verify leave type
        lt = self.db.get(LeaveType, data.leave_type_id)
        if not lt:
            raise ValueError(f"Leave type with id {data.leave_type_id} not found")
        if not lt.is_active:
            raise ValueError(f"Leave type '{lt.name}' is not active")

        # Enforce Extra leaves validation (must have reason and document upload)
        if lt.requires_document:
            if not data.reason or not data.reason.strip():
                raise ValueError("Reason is mandatory for extra leaves")
            if not data.document_url or not data.document_url.strip():
                raise ValueError("Document upload is mandatory for extra leaves")

        # Calculate total working days
        if data.is_half_day:
            total_days = 0.5
        else:
            total_days = float(self._count_working_days(data.from_date, data.to_date))

        year = data.from_date.year

        # Ensure balance exists for this employee and leave type
        balance = self._ensure_balance_exists(emp_id, lt.id, year)
        if not balance.id:
            # New balance — set total_allowed from leave type
            balance.total_allowed = lt.days_per_year
            self.db.add(balance)
            self.db.commit()
            self.db.refresh(balance)

        # Re-fetch balance with row-level lock to prevent race condition
        balance = self.db.scalar(
            select(LeaveBalance)
            .where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type_id == lt.id,
                LeaveBalance.year == year,
            )
            .with_for_update()  # Lock the row to prevent concurrent over-allocation
        )

        # Check sufficient balance
        remaining = (
            float(balance.total_allowed)
            + float(balance.carried_forward)
            - float(balance.used)
        )
        if remaining < total_days:
            raise ValueError(
                f"Insufficient leave balance. Requested {total_days} day(s), "
                f"but only {remaining:.2f} day(s) remaining."
            )

        # Check for overlapping PENDING or APPROVED requests
        overlap = None
        existing_requests = self.db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == emp_id,
                LeaveRequest.status.in_(["PENDING", "APPROVED"]),
                LeaveRequest.from_date <= data.to_date,
                LeaveRequest.to_date >= data.from_date,
            )
        ).all()

        for ext in existing_requests:
            if data.is_half_day:
                if not ext.is_half_day:
                    overlap = ext
                    break
                elif ext.from_date == data.from_date and ext.half_day_session == data.half_day_session:
                    overlap = ext
                    break
            else:
                overlap = ext
                break

        if overlap:
            overlap_desc = f"{overlap.from_date}"
            if overlap.is_half_day:
                overlap_desc += f" ({overlap.half_day_session.replace('_', ' ').title()})"
            raise ValueError(
                f"Leave request overlaps with an existing {overlap.status} request "
                f"({overlap_desc})."
            )

        req = LeaveRequest(
            employee_id=emp_id,
            leave_type_id=lt.id,
            from_date=data.from_date,
            to_date=data.to_date,
            total_days=total_days,
            reason=data.reason,
            document_url=data.document_url,
            status="PENDING",
            is_half_day=data.is_half_day,
            half_day_session=data.half_day_session,
        )
        try:
            self.db.add(req)
            self.db.flush()  # assign req.id before audit, still inside the txn

            # Initialize Approval Flow
            from app.services.approval_service import ApprovalService
            approval_svc = ApprovalService(self.db, self.current_user_id)
            flow_status = approval_svc.initialize_approval_flow("LEAVE", req.id, emp_id)

            if flow_status == "APPROVED":
                req.status = "APPROVED"
                req.approved_by = self.current_user_id
                req.approved_at = datetime.now(timezone.utc)
                # Recompute used balance
                self._recompute_used(emp_id, lt.id, year)
                # Create ON_LEAVE attendance records
                self._create_on_leave_attendance(req)
                # Trigger Task Continuity Engine
                try:
                    from app.services.task_continuity_service import TaskContinuityService
                    continuity_svc = TaskContinuityService(self.db, self.current_user_id)
                    continuity_svc.detect_and_create_task_risks(emp_id, req)
                except Exception:
                    pass

            AuditService.log(
                self.db,
                "leave_request",
                req.id,
                "APPLY",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(emp_id),
                    "leave_type": lt.code,
                    "from_date": str(data.from_date),
                    "to_date": str(data.to_date),
                    "total_days": total_days,
                },
            )
            self.db.commit()
            self.db.refresh(req)
            return _build_request_response(req)
        except Exception:
            self.db.rollback()
            raise

    def update_leave_request(
        self, id: UUID, data: LeaveRequestUpdate
    ) -> LeaveRequestResponse:
        req = self.db.get(LeaveRequest, id)
        if not req:
            raise ValueError(f"Leave request with id {id} not found")

        # Only the employee who applied can update reason, only if PENDING
        if req.employee_id != self.current_user_id:
            raise ValueError("You can only update your own leave requests")
        if req.status != "PENDING":
            raise ValueError("Only PENDING requests can be updated")

        update_data = data.model_dump(exclude_unset=True)
        try:
            for key, value in update_data.items():
                setattr(req, key, value)
            AuditService.log(
                self.db,
                "leave_request",
                id,
                "UPDATE",
                performed_by=self.current_user_id,
                new_value=update_data,
            )
            self.db.commit()
            self.db.refresh(req)
            return _build_request_response(req, self.db)
        except Exception:
            self.db.rollback()
            raise

    def cancel_leave(self, id: UUID) -> LeaveRequestResponse:
        req = self.db.get(LeaveRequest, id)
        if not req:
            raise ValueError(f"Leave request with id {id} not found")

        if req.employee_id != self.current_user_id:
            raise ValueError("You can only cancel your own leave requests")

        if req.status not in ("PENDING", "APPROVED"):
            raise ValueError(
                f"Only PENDING or APPROVED requests can be cancelled. Current status: {req.status}"
            )

        old_status = req.status
        try:
            req.status = "CANCELLED"
            
            if old_status == "APPROVED":
                # Delete corresponding ON_LEAVE attendance records
                self._delete_on_leave_attendance(req)
                
                # Recompute used leaves
                year = req.from_date.year
                self._recompute_used(req.employee_id, req.leave_type_id, year)

            AuditService.log(
                self.db,
                "leave_request",
                id,
                "CANCEL",
                performed_by=self.current_user_id,
                old_value={"status": old_status},
                new_value={"status": "CANCELLED"},
            )
            self.db.commit()
            self.db.refresh(req)
            return _build_request_response(req, self.db)
        except Exception:
            self.db.rollback()
            raise

    def approve_or_reject(
        self, id: UUID, data: LeaveApprovalRequest
    ) -> LeaveRequestResponse:
        req = self.db.get(LeaveRequest, id)
        if not req:
            raise ValueError(f"Leave request with id {id} not found")

        if req.status != "PENDING":
            raise ValueError(
                f"Only PENDING requests can be approved or rejected. Current status: {req.status}"
            )

        # H9: an approver cannot approve/reject their own leave request.
        if req.employee_id == self.current_user_id:
            raise ValueError("You cannot approve your own leave request")

        action = data.action.upper()
        if action not in ("APPROVED", "REJECTED"):
            raise ValueError("action must be 'APPROVED' or 'REJECTED'")

        if action == "REJECTED" and not data.rejection_reason:
            raise ValueError("rejection_reason is required when rejecting a leave request")

        try:
            year = req.from_date.year

            # H4: re-validate remaining balance at approval time to prevent
            # over-allocation. Multiple PENDING requests can each pass the
            # apply-time (APPROVED-only) check, so we must re-check here with a
            # row-level lock before flipping this request to APPROVED.
            if action == "APPROVED":
                balance = self.db.scalar(
                    select(LeaveBalance)
                    .where(
                        LeaveBalance.employee_id == req.employee_id,
                        LeaveBalance.leave_type_id == req.leave_type_id,
                        LeaveBalance.year == year,
                    )
                    .with_for_update()  # lock to prevent concurrent over-allocation
                )
                if balance:
                    entitlement = (
                        float(balance.total_allowed) + float(balance.carried_forward)
                    )
                    # Already-approved usage excluding this (still-PENDING) request.
                    used_other = self.db.scalar(
                        select(func.coalesce(func.sum(LeaveRequest.total_days), 0)).where(
                            LeaveRequest.employee_id == req.employee_id,
                            LeaveRequest.leave_type_id == req.leave_type_id,
                            LeaveRequest.status == "APPROVED",
                            func.extract("year", LeaveRequest.from_date) == year,
                        )
                    ) or 0.0
                    projected_used = float(used_other) + float(req.total_days)
                    if projected_used > entitlement:
                        remaining = entitlement - float(used_other)
                        raise ValueError(
                            f"Insufficient leave balance to approve. Requested "
                            f"{float(req.total_days)} day(s), but only {remaining:.2f} "
                            f"day(s) remaining."
                        )

            req.status = action
            req.approved_by = self.current_user_id
            req.approved_at = datetime.now(timezone.utc)

            if data.rejection_reason is not None:
                req.rejection_reason = data.rejection_reason
            if data.hr_notes is not None:
                req.hr_notes = data.hr_notes

            if action == "APPROVED":
                # Recompute used balance (flush-only) — now inside the txn,
                # before the single commit, so approval decrements the balance.
                self._recompute_used(req.employee_id, req.leave_type_id, year)

                # Create ON_LEAVE attendance records
                self._create_on_leave_attendance(req)

                # Trigger Task Continuity Engine (before commit).
                from app.services.task_continuity_service import TaskContinuityService
                continuity_svc = TaskContinuityService(self.db, self.current_user_id)
                continuity_svc.detect_and_create_task_risks(req.employee_id, req)

            AuditService.log(
                self.db,
                "leave_request",
                id,
                action,
                performed_by=self.current_user_id,
                old_value={"status": "PENDING"},
                new_value={"status": action},
            )

            self.db.commit()
            self.db.refresh(req)
            return _build_request_response(req, self.db)
        except Exception:
            self.db.rollback()
            raise
