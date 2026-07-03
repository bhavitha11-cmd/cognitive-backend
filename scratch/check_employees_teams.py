import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.services.employee_service import EmployeeService

db = SessionLocal()
try:
    service = EmployeeService(db)
    employees, total = service.get_all(limit=200, account_status="ACTIVE")
    print(f"Total active employees: {total}")
    for emp in employees:
        # Load the team_id using the schemas representation or from database model relationship
        # Let's inspect the keys/relationships of the employee
        team_id = getattr(emp, "team_id", None)
        print(f"ID: {emp.id} | Name: {emp.first_name} {emp.last_name} | Team ID: {team_id}")
        
        # Let's check team_members mappings
        from app.models.team_member import TeamMember
        tms = db.query(TeamMember).filter(TeamMember.employee_id == emp.id).all()
        for tm in tms:
            print(f"  -> Member of Team: {tm.team_id} (Role: {tm.role_in_team}, Primary: {tm.is_primary_team})")
finally:
    db.close()
