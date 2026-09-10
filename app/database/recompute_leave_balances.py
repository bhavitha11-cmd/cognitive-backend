import logging
from sqlalchemy import select, func
from app.database.session import SessionLocal
from app.models.employee import Employee
from app.models.leave_balance import LeaveBalance
from app.models.leave_request import LeaveRequest
from app.models.leave_type import LeaveType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recompute_leave_balances")

def sync_all_leave_balances(year: int = 2026):
    db = SessionLocal()
    try:
        employees = db.scalars(select(Employee)).all()
        leave_types = db.scalars(select(LeaveType).where(LeaveType.is_active.is_(True))).all()
        
        updated_count = 0
        for emp in employees:
            for lt in leave_types:
                # Find balance record
                balance = db.scalars(
                    select(LeaveBalance).where(
                        LeaveBalance.employee_id == emp.id,
                        LeaveBalance.leave_type_id == lt.id,
                        LeaveBalance.year == year,
                    )
                ).first()
                
                # Calculate expected total_allowed with proration based on joining date
                days_allowed = float(lt.days_per_year)
                if emp.date_of_joining:
                    if emp.date_of_joining.year == year:
                        joining_month = emp.date_of_joining.month
                        remaining_months = 12 - joining_month + 1
                        prorated = (days_allowed * remaining_months) / 12.0
                        days_allowed = round(prorated * 2) / 2.0
                    elif emp.date_of_joining.year > year:
                        days_allowed = 0.0

                # Calculate actual approved total_days
                actual_used = db.scalar(
                    select(func.coalesce(func.sum(LeaveRequest.total_days), 0.0)).where(
                        LeaveRequest.employee_id == emp.id,
                        LeaveRequest.leave_type_id == lt.id,
                        LeaveRequest.status == "APPROVED",
                        func.extract("year", LeaveRequest.from_date) == year,
                    )
                ) or 0.0

                if balance:
                    updated = False
                    if float(balance.used) != float(actual_used):
                        logger.info(
                            f"Updating used for {emp.first_name} {emp.last_name} ({lt.code}): "
                            f"Old Used = {balance.used}, New Used = {actual_used}"
                        )
                        balance.used = float(actual_used)
                        updated = True
                    if float(balance.total_allowed) != float(days_allowed):
                        logger.info(
                            f"Updating total_allowed for {emp.first_name} {emp.last_name} ({lt.code}): "
                            f"Old Allowed = {balance.total_allowed}, New Allowed = {days_allowed}"
                        )
                        balance.total_allowed = float(days_allowed)
                        updated = True
                    if updated:
                        db.add(balance)
                        updated_count += 1
                else:
                    logger.info(
                        f"Creating missing balance for {emp.first_name} {emp.last_name} ({lt.code}): "
                        f"Allowed = {days_allowed}, Used = {actual_used}"
                    )
                    new_bal = LeaveBalance(
                        employee_id=emp.id,
                        leave_type_id=lt.id,
                        year=year,
                        total_allowed=float(days_allowed),
                        used=float(actual_used),
                        carried_forward=0.0,
                    )
                    db.add(new_bal)
                    updated_count += 1

        db.commit()
        logger.info(f"Successfully synced leave balances. Total updated/created: {updated_count}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error syncing leave balances: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    sync_all_leave_balances(2026)

