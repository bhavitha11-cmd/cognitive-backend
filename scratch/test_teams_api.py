import sys
import os
from uuid import UUID

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.services.team_service import TeamService

db = SessionLocal()
try:
    service = TeamService(db)
    # Test getting all teams
    print("--- ALL TEAMS FROM SERVICE ---")
    teams = service.get_all()
    for t in teams:
        print(f"ID: {t.id} | Name: {t.team_name} | Dept ID: {t.department_id}")
        
    # Test getting teams by department
    dept_id = UUID("fe4bdc24-21ac-4210-8289-d0e848105c2e")
    print(f"\n--- TEAMS FOR DEPT {dept_id} ---")
    teams_dept = service.get_all(department_id=dept_id)
    for t in teams_dept:
        print(f"ID: {t.id} | Name: {t.team_name} | Dept ID: {t.department_id}")
finally:
    db.close()
