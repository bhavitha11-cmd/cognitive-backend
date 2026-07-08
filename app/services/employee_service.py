import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_password_hash, verify_password
from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.employee_role_history import EmployeeRoleHistory
from app.models.employee_reporting_history import EmployeeReportingHistory
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
    EmployeeLookupItem,
    EmployeeOffboardCheck,
    EmployeeOffboardBlocker,
)
from app.services.audit_service import AuditService

# Valid status transitions state machine.
# Every non-terminal status may transition to RESIGNED or TERMINATED so the
# offboarding workflow is never blocked by the state machine.
STATUS_TRANSITIONS = {
    "ACTIVE": {"PROBATION", "ON_LEAVE", "NOTICE_PERIOD", "SUSPENDED", "RESIGNED", "TERMINATED"},
    "PROBATION": {"ACTIVE", "ON_LEAVE", "NOTICE_PERIOD", "SUSPENDED", "RESIGNED", "TERMINATED"},
    "ON_LEAVE": {"ACTIVE", "NOTICE_PERIOD", "SUSPENDED", "RESIGNED", "TERMINATED"},
    "SUSPENDED": {"ACTIVE", "NOTICE_PERIOD", "RESIGNED", "TERMINATED"},
    "NOTICE_PERIOD": {"ACTIVE", "SUSPENDED", "RESIGNED", "TERMINATED"},
    "RESIGNED": set(),
    "TERMINATED": set(),
}

TERMINAL_STATUSES = {"RESIGNED", "TERMINATED"}


class EmployeeService:
    def __init__(self, db: Session, current_user_id=None):
        self.db = db
        self.repo = EmployeeRepository(db)
        self.current_user_id = current_user_id

    def _resolve_id(self, id_str: str) -> UUID:
        try:
            return UUID(id_str)
        except ValueError:
            pass
        emp = self.repo.get_by_employee_code(id_str)
        if emp:
            return emp.id
        raise ValueError(f"Employee with id or code '{id_str}' not found")

    def _generate_employee_code(self) -> str:
        from sqlalchemy import func as _func, cast, Integer
        # Compute the max numeric suffix so codes stay monotonic beyond EMP-999.
        # (String MAX would rank "EMP-99" above "EMP-100".)
        max_num = self.repo.db.scalar(
            select(
                _func.max(
                    cast(_func.split_part(Employee.employee_code, "-", 2), Integer)
                )
            ).where(Employee.employee_code.like("EMP-%"))
        )
        next_num = (max_num or 0) + 1
        return f"EMP-{next_num:03d}"

    def _build_list_response(self, employee: Employee) -> EmployeeListResponse:
        role_ids = [str(er.role_id) for er in employee.employee_roles if er.is_active]
        role_names = [
            er.role.name for er in employee.employee_roles if er.is_active and er.role
        ]
        reporting_manager_name = None
        if employee.reporting_manager:
            reporting_manager_name = (
                f"{employee.reporting_manager.first_name} {employee.reporting_manager.last_name}"
            )
            
        # Check if department head
        is_dept_head = False
        if employee.department_id:
            dept = self.db.get(Department, employee.department_id)
            if dept and dept.department_head_id == employee.id:
                is_dept_head = True
        
        # Get active team assignment
        active_assignment = next((ta for ta in employee.team_assignments if ta.left_at is None), None)
        team_id = active_assignment.team_id if active_assignment else None
        team_name = active_assignment.team.team_name if active_assignment and active_assignment.team else None
        role_in_team = active_assignment.role_in_team if active_assignment else None

        return EmployeeListResponse(
            id=employee.id,
            employee_code=employee.employee_code,
            first_name=employee.first_name,
            middle_name=employee.middle_name,
            last_name=employee.last_name,
            display_name=employee.display_name,
            official_email=employee.official_email,
            personal_email=employee.personal_email,
            email=employee.email,
            username=employee.username,
            phone=employee.phone,
            mobile_number=employee.mobile_number,
            alternate_phone=employee.alternate_phone,
            gender=employee.gender,
            date_of_birth=employee.date_of_birth,
            profile_photo_url=employee.profile_photo_url,
            department_id=employee.department_id,
            reporting_manager_id=employee.reporting_manager_id,
            date_of_joining=employee.date_of_joining,
            employment_type=employee.employment_type,
            account_status=employee.account_status,
            is_active=employee.is_active,
            emergency_contact_name=employee.emergency_contact_name,
            emergency_contact_phone=employee.emergency_contact_phone,
            address=employee.address,
            created_at=employee.created_at,
            updated_at=employee.updated_at,
            designation_id=employee.designation_id,
            designation_name=employee.designation.name if employee.designation else None,
            department_name=employee.department.name if employee.department else None,
            reporting_manager_name=reporting_manager_name,
            role_ids=role_ids,
            role_names=role_names,
            is_department_head=is_dept_head,
            team_id=team_id,
            team_name=team_name,
            role_in_team=role_in_team,
        )

    def get_all(
        self,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
        department_id: UUID | None = None,
        account_status: str | None = None,
    ) -> tuple[list[EmployeeListResponse], int]:
        from sqlalchemy import func as sqlfunc
        base_query = (
            select(Employee)
            .options(
                joinedload(Employee.department),
                joinedload(Employee.designation),
                joinedload(Employee.reporting_manager),
                joinedload(Employee.employee_roles).joinedload(EmployeeRole.role),
            )
        )
        if search:
            search_term = f"%{search}%"
            base_query = base_query.where(
                or_(
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term),
                    Employee.email.ilike(search_term),
                    Employee.employee_code.ilike(search_term),
                )
            )
        if department_id:
            base_query = base_query.where(Employee.department_id == department_id)
        if account_status:
            base_query = base_query.where(Employee.account_status == account_status.upper())
        count_query = select(sqlfunc.count()).select_from(
            base_query.with_only_columns(Employee.id).subquery()
        )
        total = self.repo.db.scalar(count_query) or 0
        base_query = base_query.order_by(Employee.created_at.desc()).offset(skip).limit(limit)
        employees = self.repo.db.scalars(base_query).unique().all()
        return [self._build_list_response(emp) for emp in employees], total

    def get_by_id(self, id: UUID) -> EmployeeListResponse:
        employee = (
            self.repo.db.scalars(
                select(Employee)
                .options(
                    joinedload(Employee.department),
                    joinedload(Employee.designation),
                    joinedload(Employee.reporting_manager),
                    joinedload(Employee.employee_roles).joinedload(EmployeeRole.role),
                )
                .where(Employee.id == id)
            )
            .unique()
            .first()
        )
        if not employee:
            raise ValueError(f"Employee with id {id} not found")
        return self._build_list_response(employee)

    def get_lookup(self) -> list[EmployeeLookupItem]:
        employees = self.repo.get_lookup()
        result = []
        for e in employees:
            display_name = e.display_name or f"{e.first_name} {e.last_name}".strip()
            role_ids = [er.role_id for er in e.employee_roles if er.is_active]
            active_assignment = next((ta for ta in e.team_assignments if ta.left_at is None), None)
            team_id = active_assignment.team_id if active_assignment else None
            result.append(EmployeeLookupItem(
                id=e.id,
                display_name=display_name,
                employee_code=e.employee_code,
                department_id=e.department_id,
                role_ids=role_ids,
                team_id=team_id
            ))
        return result

    def create(self, data: EmployeeCreate) -> EmployeeResponse:
        if self.repo.get_by_email(data.email):
            raise ValueError(f"Employee with email '{data.email}' already exists")
        if self.repo.get_by_username(data.username):
            raise ValueError(f"Employee with username '{data.username}' already exists")
        if data.reporting_manager_id:
            self._validate_manager(data.reporting_manager_id)
            self._detect_circular_reporting(None, data.reporting_manager_id)

        if data.department_id:
            dept = self.db.get(Department, data.department_id)
            if dept and not dept.is_active:
                raise ValueError("Cannot assign employee to an inactive department")

        status = data.account_status.upper() if data.account_status else "ACTIVE"
        if status not in STATUS_TRANSITIONS:
            raise ValueError(f"Invalid account status: {status}")

        # C2: privilege-escalation guard on create (new employee has no existing roles).
        if data.role_ids:
            self._validate_role_assignment(None, data.role_ids, existing_role_ids=set())

        is_dept_head = data.is_department_head
        team_id = data.team_id
        is_team_lead = data.is_team_lead

        employee_data = data.model_dump(exclude={"password", "role_ids", "is_department_head", "team_id", "is_team_lead"})
        employee_data["account_status"] = status
        employee_data["password_hash"] = get_password_hash(data.password)

        if not employee_data.get("display_name"):
            employee_data["display_name"] = f"{data.first_name} {data.last_name}".strip()

        try:
            from sqlalchemy.exc import IntegrityError as _IntegrityError
            for _attempt in range(3):
                employee_data["employee_code"] = self._generate_employee_code()
                employee = Employee(**employee_data)
                self.db.add(employee)
                try:
                    self.db.flush()  # get ID without committing
                    break
                except _IntegrityError as _ie:
                    self.db.rollback()
                    if "employee_code" in str(_ie.orig) and _attempt < 2:
                        continue
                    raise

            for role_id in data.role_ids:
                emp_role = __import__("app.models.employee_role", fromlist=["EmployeeRole"]).EmployeeRole(
                    employee_id=employee.id, role_id=role_id
                )
                self.db.add(emp_role)

            # Handle Department Head setting
            if is_dept_head and employee.department_id:
                dept = self.db.get(Department, employee.department_id)
                if dept:
                    dept.department_head_id = employee.id
                    self.db.add(dept)

            # Handle Team assignment
            if team_id:
                from app.models.team_member import TeamMember
                role_in_team = "LEAD" if is_team_lead else "MEMBER"
                if is_team_lead:
                    old_leads = self.db.scalars(
                        select(TeamMember).where(
                            TeamMember.team_id == team_id,
                            TeamMember.role_in_team == "LEAD",
                            TeamMember.left_at.is_(None),
                        )
                    ).all()
                    for ol in old_leads:
                        ol.role_in_team = "MEMBER"
                        self.db.add(ol)
                new_member = TeamMember(
                    team_id=team_id,
                    employee_id=employee.id,
                    role_in_team=role_in_team,
                    is_primary_team=True,
                )
                self.db.add(new_member)

            AuditService.log(
                self.db, "employee", employee.id, "CREATE",
                performed_by=self.current_user_id,
                new_value={"employee_code": employee.employee_code, "email": data.email},
            )
            self.db.commit()
            self.db.refresh(employee)
            # Invalidate hierarchy cache on successful create
            from app.core.hierarchy_cache import HierarchyCache
            HierarchyCache.get_instance().invalidate()
        except Exception:
            self.db.rollback()
            raise

        return EmployeeResponse.model_validate(employee)

    def update(self, id: UUID, data: EmployeeUpdate) -> EmployeeResponse:
        employee = self.repo.get_by_id(id)
        if not employee:
            raise ValueError(f"Employee with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        if "email" in update_data and update_data["email"] != employee.email:
            existing = self.repo.get_by_email(update_data["email"])
            if existing and existing.id != id:
                raise ValueError(f"Employee with email '{update_data['email']}' already exists")

        if "username" in update_data and update_data["username"] != employee.username:
            existing = self.repo.get_by_username(update_data["username"])
            if existing and existing.id != id:
                raise ValueError(f"Employee with username '{update_data['username']}' already exists")

        if "reporting_manager_id" in update_data:
            new_mgr = update_data["reporting_manager_id"]
            if new_mgr == id:
                raise ValueError("Employee cannot report to themselves")
            if new_mgr:
                self._validate_manager(new_mgr)
                self._detect_circular_reporting(id, new_mgr)
            if new_mgr != employee.reporting_manager_id:
                self._record_reporting_change(
                    employee, employee.reporting_manager_id, new_mgr
                )

        if "password" in update_data:
            update_data["password_hash"] = get_password_hash(update_data.pop("password"))

        if "account_status" in update_data:
            new_status = update_data["account_status"].upper()
            old_status = employee.account_status
            # H6: terminal statuses must go through the offboarding wizard so that
            # ownership transfers / blockers are handled. Reject direct PUT here.
            if new_status in TERMINAL_STATUSES and old_status not in TERMINAL_STATUSES:
                raise ValueError(
                    "Cannot set a terminal status (RESIGNED/TERMINATED) via update. "
                    "Use the offboarding workflow (/offboard/execute) instead."
                )
            self._validate_status_transition(old_status, new_status)
            update_data["account_status"] = new_status
            # Keep is_active consistent with the (non-terminal) status.
            update_data["is_active"] = new_status not in TERMINAL_STATUSES

        role_ids = update_data.pop("role_ids", None)

        # C2: privilege-escalation guard on update, BEFORE any mutation.
        if role_ids is not None:
            existing = {str(er.role_id) for er in self.repo.get_employee_roles(id)}
            self._validate_role_assignment(id, role_ids, existing_role_ids=existing)

        is_dept_head = update_data.pop("is_department_head", None)
        team_id = update_data.pop("team_id", None)
        is_team_lead = update_data.pop("is_team_lead", None)

        old_dept_id = employee.department_id

        old_values = {k: getattr(employee, k, None) for k in update_data if k != "password_hash"}
        employee = self.repo.update(employee, update_data)

        if role_ids is not None:
            self._sync_roles(employee, role_ids)

        # Department head assignment
        if is_dept_head is not None or (employee.department_id != old_dept_id):
            if old_dept_id and old_dept_id != employee.department_id:
                old_dept = self.db.get(Department, old_dept_id)
                if old_dept and old_dept.department_head_id == employee.id:
                    old_dept.department_head_id = None
                    self.db.add(old_dept)
            
            if is_dept_head is True or (is_dept_head is None and employee.department_id != old_dept_id and old_dept_id and self.db.get(Department, old_dept_id).department_head_id == employee.id):
                if employee.department_id:
                    new_dept = self.db.get(Department, employee.department_id)
                    if new_dept:
                        new_dept.department_head_id = employee.id
                        self.db.add(new_dept)
            elif is_dept_head is False:
                if employee.department_id:
                    curr_dept = self.db.get(Department, employee.department_id)
                    if curr_dept and curr_dept.department_head_id == employee.id:
                        curr_dept.department_head_id = None
                        self.db.add(curr_dept)
            self.db.commit()

        # Team assignment logic
        from app.models.team_member import TeamMember
        active_assignment = next((ta for ta in employee.team_assignments if ta.left_at is None), None)

        if team_id is not None or is_team_lead is not None:
            target_team_id = team_id if team_id is not None else (active_assignment.team_id if active_assignment else None)
            target_is_lead = is_team_lead if is_team_lead is not None else (active_assignment.role_in_team == "LEAD" if active_assignment else False)
            target_role = "LEAD" if target_is_lead else "MEMBER"

            if target_team_id:
                # If they are already active in target_team_id, just update their role
                if active_assignment and active_assignment.team_id == target_team_id:
                    if active_assignment.role_in_team != target_role:
                        # If becoming lead, demote other leads of this team
                        if target_role == "LEAD":
                            old_leads = self.db.scalars(
                                select(TeamMember).where(
                                    TeamMember.team_id == target_team_id,
                                    TeamMember.role_in_team == "LEAD",
                                    TeamMember.left_at.is_(None)
                                )
                            ).all()
                            for ol in old_leads:
                                ol.role_in_team = "MEMBER"
                                self.db.add(ol)
                        active_assignment.role_in_team = target_role
                        self.db.add(active_assignment)
                else:
                    # They are changing teams or joining a team for the first time
                    # 1. Deactivate old assignments
                    for ta in employee.team_assignments:
                        if ta.left_at is None:
                            ta.left_at = datetime.now(timezone.utc)
                            ta.is_primary_team = False
                            self.db.add(ta)
                    
                    # Flush deactivations to database immediately to release uq_team_members_primary_team constraint
                    self.db.flush()
                    
                    # 2. If becoming lead, demote other leads of target team
                    if target_role == "LEAD":
                        old_leads = self.db.scalars(
                            select(TeamMember).where(
                                TeamMember.team_id == target_team_id,
                                TeamMember.role_in_team == "LEAD",
                                TeamMember.left_at.is_(None)
                            )
                        ).all()
                        for ol in old_leads:
                            ol.role_in_team = "MEMBER"
                            self.db.add(ol)
                    
                    # 3. Check if there is already a historical row in team_members for this employee and team
                    existing_tm = self.db.scalars(
                        select(TeamMember).where(
                            TeamMember.team_id == target_team_id,
                            TeamMember.employee_id == employee.id
                        )
                    ).first()
                    
                    if existing_tm:
                        # Reactivate and update role
                        existing_tm.left_at = None
                        existing_tm.role_in_team = target_role
                        existing_tm.is_primary_team = True
                        self.db.add(existing_tm)
                    else:
                        # Create new
                        new_assignment = TeamMember(
                            team_id=target_team_id,
                            employee_id=employee.id,
                            role_in_team=target_role,
                            is_primary_team=True
                        )
                        self.db.add(new_assignment)
            else:
                # Remove from all teams
                for ta in employee.team_assignments:
                    if ta.left_at is None:
                        ta.left_at = datetime.now(timezone.utc)
                        ta.is_primary_team = False
                        self.db.add(ta)
            self.db.commit()

        # Sanitize sensitive fields before passing to the audit log
        _sensitive = ('password_hash', 'password', 'hashed_password')
        log_old = {k: v for k, v in old_values.items() if k not in _sensitive} if old_values else None
        log_new = {k: v for k, v in update_data.items() if k not in _sensitive} if update_data else None
        try:
            AuditService.log(
                self.db, "employee", id, "UPDATE",
                performed_by=self.current_user_id,
                old_value=log_old if log_old else None,
                new_value=log_new if log_new else None,
            )
            self.db.commit()
            # Invalidate hierarchy cache on successful update
            from app.core.hierarchy_cache import HierarchyCache
            HierarchyCache.get_instance().invalidate()
        except Exception:
            self.db.rollback()
            raise
        return EmployeeResponse.model_validate(employee)

    def offboard_check(self, id: UUID) -> EmployeeOffboardCheck:
        employee = self.repo.get_by_id(id)
        if not employee:
            raise ValueError(f"Employee with id {id} not found")

        blockers = []

        # Check 1: Direct reports
        direct_reports = self.repo.get_direct_reports(id)
        if direct_reports:
            blockers.append(EmployeeOffboardBlocker(
                type="direct_reports",
                count=len(direct_reports),
                items=[
                    {"id": str(e.id), "name": f"{e.first_name} {e.last_name}"}
                    for e in direct_reports
                ],
            ))

        # Check 2: Team ownership (LEAD role)
        managed_teams = self.repo.get_managed_teams(id)
        if managed_teams:
            blockers.append(EmployeeOffboardBlocker(
                type="team_ownership",
                count=len(managed_teams),
                items=[
                    {
                        "id": str(mt.team_id),
                        "name": mt.team.team_name if mt.team else "Unknown",
                        "members_count": len(mt.team.members) if mt.team else 0,
                    }
                    for mt in managed_teams if mt.team
                ],
            ))

        # Check 3: Department head ownership
        headed_depts = self.repo.get_headed_departments(id)
        if headed_depts:
            blockers.append(EmployeeOffboardBlocker(
                type="department_ownership",
                count=len(headed_depts),
                items=[
                    {
                        "id": str(d.id),
                        "name": d.name,
                        "employees_count": len(d.employees),
                    }
                    for d in headed_depts
                ],
            ))

        return EmployeeOffboardCheck(
            employee_id=employee.id,
            employee_name=f"{employee.first_name} {employee.last_name}",
            current_status=employee.account_status,
            can_offboard=len(blockers) == 0,
            blockers=blockers,
        )

    def transfer_reports(self, employee_id: UUID, new_manager_id: UUID, report_ids: list[UUID]) -> list[EmployeeResponse]:
        employee = self.repo.get_by_id(employee_id)
        if not employee:
            raise ValueError(f"Source employee with id {employee_id} not found")
        new_manager = self.repo.get_by_id(new_manager_id)
        if not new_manager:
            raise ValueError(f"Target manager with id {new_manager_id} not found")
        if not new_manager.is_active:
            raise ValueError("Target manager is not active")

        results = []
        for rid in report_ids:
            report = self.repo.get_by_id(rid)
            if not report:
                continue
            if report.reporting_manager_id != employee_id:
                continue
            old_mgr_id = report.reporting_manager_id
            self.repo.update(report, {"reporting_manager_id": new_manager_id})
            self._record_reporting_change(report, old_mgr_id, new_manager_id)
            results.append(EmployeeResponse.model_validate(report))
        AuditService.log(
            self.db, "employee", employee_id, "TRANSFER_REPORTS",
            performed_by=self.current_user_id,
            new_value={
                "new_manager_id": str(new_manager_id),
                "transferred_report_ids": [str(rid) for rid in report_ids],
            },
        )
        return results

    def transfer_teams(self, employee_id: UUID, new_lead_id: UUID, team_ids: list[UUID]) -> None:
        from app.repositories.team_member_repository import TeamMemberRepository
        member_repo = TeamMemberRepository(self.db)

        new_lead = self.repo.get_by_id(new_lead_id)
        if not new_lead or not new_lead.is_active:
            raise ValueError("Target team lead is not active")

        for team_id in team_ids:
            member = member_repo.get_by_team_and_employee(team_id, employee_id)
            if not member or member.left_at is not None:
                continue
            member_repo.update(member, {
                "left_at": datetime.now(timezone.utc),
                "is_primary_team": False,
            })
            # Assign new lead
            existing_new = member_repo.get_by_team_and_employee(team_id, new_lead_id)
            if existing_new and existing_new.left_at is None:
                member_repo.update(existing_new, {"role_in_team": "LEAD"})
            elif existing_new and existing_new.left_at is not None:
                member_repo.update(existing_new, {
                    "left_at": None,
                    "role_in_team": "LEAD",
                    "joined_at": date.today().isoformat(),
                })
            else:
                from app.models.team_member import TeamMember
                new_member = TeamMember(
                    team_id=team_id,
                    employee_id=new_lead_id,
                    role_in_team="LEAD",
                    joined_at=date.today(),
                )
                self.db.add(new_member)
        self.db.commit()
        AuditService.log(
            self.db, "employee", employee_id, "TRANSFER_TEAMS",
            performed_by=self.current_user_id,
            new_value={
                "new_lead_id": str(new_lead_id),
                "transferred_team_ids": [str(tid) for tid in team_ids],
            },
        )

    def transfer_departments(self, employee_id: UUID, new_head_id: UUID, department_ids: list[UUID]) -> None:
        new_head = self.repo.get_by_id(new_head_id)
        if not new_head or not new_head.is_active:
            raise ValueError("Target department head is not active")
        for dept_id in department_ids:
            dept = self.db.get(Department, dept_id)
            if dept and dept.department_head_id == employee_id:
                dept.department_head_id = new_head_id
        self.db.commit()
        AuditService.log(
            self.db, "employee", employee_id, "TRANSFER_DEPARTMENTS",
            performed_by=self.current_user_id,
            new_value={
                "new_head_id": str(new_head_id),
                "transferred_department_ids": [str(did) for did in department_ids],
            },
        )

    def offboard_confirm(self, id: UUID, final_status: str = "RESIGNED") -> EmployeeResponse:
        check = self.offboard_check(id)
        if not check.can_offboard:
            raise ValueError(
                f"Cannot offboard employee. Blockers: {[b.type for b in check.blockers]}"
            )
        employee = self.repo.get_by_id(id)
        if not employee:
            raise ValueError(f"Employee with id {id} not found")
        self._validate_status_transition(employee.account_status, final_status)
        old_status = employee.account_status
        employee = self.repo.update(employee, {
            "account_status": final_status,
            "is_active": final_status not in TERMINAL_STATUSES,
        })
        AuditService.log(
            self.db, "employee", id, "OFFBOARD",
            performed_by=self.current_user_id,
            old_value={"account_status": old_status},
            new_value={"account_status": final_status},
        )
        return EmployeeResponse.model_validate(employee)

    def deactivate(self, id: UUID) -> EmployeeResponse:
        employee = self.repo.get_by_id(id)
        if not employee:
            raise ValueError(f"Employee with id {id} not found")
        check = self.offboard_check(id)
        if not check.can_offboard:
            raise ValueError(
                f"Cannot deactivate employee. Use offboarding workflow. "
                f"Blockers: {[b.type for b in check.blockers]}"
            )
        return self.offboard_confirm(id, "TERMINATED")

    def delete(self, id: UUID) -> None:
        employee = self.repo.get_by_id(id)
        if not employee:
            raise ValueError(f"Employee with id {id} not found")
        if employee.account_status in TERMINAL_STATUSES:
            self.repo.delete(employee)
            AuditService.log(
                self.db, "employee", id, "DELETE",
                performed_by=self.current_user_id,
                old_value={"employee_code": employee.employee_code, "email": employee.email},
            )
            from app.core.hierarchy_cache import HierarchyCache
            HierarchyCache.get_instance().invalidate()
            return
        check = self.offboard_check(id)
        if not check.can_offboard:
            raise ValueError(
                f"Cannot delete employee with active dependencies. "
                f"Use the offboarding workflow to transfer dependencies first. "
                f"Blockers: {[b.type for b in check.blockers]}"
            )
        old_status = employee.account_status
        employee = self.repo.update(employee, {
            "account_status": "TERMINATED",
            "is_active": False,
        })
        AuditService.log(
            self.db, "employee", id, "DELETE",
            performed_by=self.current_user_id,
            old_value={"account_status": old_status},
            new_value={"account_status": "TERMINATED"},
        )
        from app.core.hierarchy_cache import HierarchyCache
        HierarchyCache.get_instance().invalidate()

    def get_role_history(self, employee_id: UUID) -> list[dict]:
        records = self.db.scalars(
            select(EmployeeRoleHistory)
            .where(EmployeeRoleHistory.employee_id == employee_id)
            .order_by(EmployeeRoleHistory.changed_at.desc())
        ).all()
        result = []
        for r in records:
            result.append({
                "id": str(r.id),
                "employee_id": str(r.employee_id),
                "old_role_id": str(r.old_role_id) if r.old_role_id else None,
                "old_role_name": r.old_role.name if r.old_role else None,
                "new_role_id": str(r.new_role_id),
                "new_role_name": r.new_role.name if r.new_role else None,
                "effective_from": r.effective_from.isoformat() if r.effective_from else None,
                "effective_to": r.effective_to.isoformat() if r.effective_to else None,
                "reason": r.reason,
                "changed_by": str(r.changed_by) if r.changed_by else None,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            })
        return result

    def get_reporting_history(self, employee_id: UUID) -> list[dict]:
        records = self.db.scalars(
            select(EmployeeReportingHistory)
            .where(EmployeeReportingHistory.employee_id == employee_id)
            .order_by(EmployeeReportingHistory.changed_at.desc())
        ).all()
        result = []
        for r in records:
            result.append({
                "id": str(r.id),
                "employee_id": str(r.employee_id),
                "old_manager_id": str(r.old_manager_id) if r.old_manager_id else None,
                "old_manager_name": (
                    f"{r.old_manager.first_name} {r.old_manager.last_name}"
                    if r.old_manager else None
                ),
                "new_manager_id": str(r.new_manager_id) if r.new_manager_id else None,
                "new_manager_name": (
                    f"{r.new_manager.first_name} {r.new_manager.last_name}"
                    if r.new_manager else None
                ),
                "reason": r.reason,
                "changed_by": str(r.changed_by) if r.changed_by else None,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            })
        return result

    def get_organization_tree(self) -> list[dict]:
        from app.services.organization_hierarchy_service import OrganizationHierarchyService
        hierarchy = OrganizationHierarchyService(self.db)
        return hierarchy.get_organization_tree()

    # ---- Private: Validation Helpers ----

    def _actor_is_super_admin(self) -> bool:
        """True if the current actor holds any is_super_admin role."""
        if not self.current_user_id:
            return False
        from app.models.role import Role
        return bool(
            self.db.scalar(
                select(Role.id)
                .join(EmployeeRole, EmployeeRole.role_id == Role.id)
                .where(
                    EmployeeRole.employee_id == self.current_user_id,
                    EmployeeRole.is_active == True,
                    Role.is_super_admin == True,
                )
                .limit(1)
            )
        )

    def _validate_role_assignment(
        self, target_id: UUID | None, new_role_ids: list, existing_role_ids: set | None = None
    ) -> None:
        """Guard against privilege escalation via role assignment (C2).

        - Every role id supplied must reference an existing role.
        - A non-super-admin actor may not grant a super-admin role.
        - A non-super-admin actor may not add new roles to their OWN account.
        Called BEFORE any mutation. `existing_role_ids` (as a set of str) lets us
        detect newly-*added* roles on update so an unchanged role set is a no-op.
        """
        from app.models.role import Role

        # Normalize incoming ids to strings for comparison.
        incoming = {str(r) for r in new_role_ids}
        if existing_role_ids is None:
            newly_added = incoming
        else:
            newly_added = incoming - {str(r) for r in existing_role_ids}

        # Validate every incoming role exists (reject unknown roles).
        for rid_str in incoming:
            try:
                rid = UUID(rid_str)
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid role id: {rid_str}")
            role = self.db.get(Role, rid)
            if not role:
                raise ValueError(f"Role with id {rid_str} does not exist")

        if not newly_added:
            return  # No roles are being added — nothing to escalate.

        actor_is_super = self._actor_is_super_admin()

        # (b) An actor may not add roles to their own account (self-elevation),
        # unless they are a super-admin.
        if (
            self.current_user_id
            and target_id is not None
            and str(target_id) == str(self.current_user_id)
            and not actor_is_super
        ):
            raise ValueError("You cannot assign roles to your own account")

        # (a) Only super-admins may grant a super-admin / higher-privileged role.
        if not actor_is_super:
            for rid_str in newly_added:
                role = self.db.get(Role, UUID(rid_str))
                if role and role.is_super_admin:
                    raise ValueError(
                        "Only a super-admin may grant the super-admin role"
                    )

    def _validate_manager(self, manager_id: UUID) -> None:
        manager = self.repo.get_by_id(manager_id)
        if not manager:
            raise ValueError(f"Manager with id {manager_id} not found")
        if not manager.is_active:
            raise ValueError("Reporting manager must be an active employee")

    def _detect_circular_reporting(self, employee_id: UUID | None, new_manager_id: UUID) -> None:
        if not employee_id:
            return
        from app.services.organization_hierarchy_service import OrganizationHierarchyService
        hierarchy = OrganizationHierarchyService(self.db)
        hierarchy.validate_reporting_change(employee_id, new_manager_id)

    def _validate_status_transition(self, old_status: str, new_status: str) -> None:
        old = old_status.upper()
        new = new_status.upper()
        if old == new:
            return
        allowed = STATUS_TRANSITIONS.get(old, set())
        if new not in allowed:
            raise ValueError(
                f"Invalid status transition from '{old}' to '{new}'. "
                f"Allowed transitions from '{old}': {allowed}"
            )

    def _record_reporting_change(
        self, employee: Employee, old_manager_id: UUID | None, new_manager_id: UUID | None
    ) -> None:
        record = EmployeeReportingHistory(
            employee_id=employee.id,
            old_manager_id=old_manager_id,
            new_manager_id=new_manager_id,
            reason="Manager reassignment",
        )
        self.db.add(record)
        self.db.flush()  # Changed from db.commit() - callers own the transaction boundary

    def _record_role_history(
        self, employee_id: UUID, old_role_id: UUID | None, new_role_id: UUID,
        reason: str = "Role assignment", changed_by: UUID | None = None
    ) -> None:
        record = EmployeeRoleHistory(
            employee_id=employee_id,
            old_role_id=old_role_id,
            new_role_id=new_role_id,
            effective_from=date.today(),
            reason=reason,
            changed_by=changed_by,
        )
        self.db.add(record)
        self.db.flush()  # Changed from db.commit() - callers own the transaction boundary

    def _sync_roles(self, employee: Employee, role_ids: list) -> None:
        existing_roles = self.repo.get_employee_roles(employee.id)
        existing_role_ids = {str(er.role_id) for er in existing_roles}
        new_role_ids = {str(r) for r in role_ids}

        # Roles to remove
        for er in existing_roles:
            if str(er.role_id) not in new_role_ids:
                self.repo.remove_role(er.id)

        # Roles to add
        for rid_str in new_role_ids - existing_role_ids:
            rid = UUID(rid_str)
            self._record_role_history(
                employee.id, None, rid,
                reason="Role assigned", changed_by=employee.updated_by,
            )
            self.repo.assign_role(employee.id, rid)

    # ---- Bulk ops (deprecated — warn only) ----

    def bulk_deactivate(self, ids: list[UUID]) -> list[EmployeeResponse]:
        raise ValueError("Bulk deactivate is deprecated. Use per-employee offboarding.")

    def bulk_delete(self, ids: list[UUID]) -> None:
        raise ValueError("Bulk delete is deprecated. Use per-employee offboarding.")

