import sys
import os

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.department import Department
from app.models.team import Team

db = SessionLocal()
try:
    print("--- DEPARTMENTS ---")
    departments = db.query(Department).all()
    for d in departments:
        print(f"ID: {d.id} | Code: {d.code} | Name: {d.name}")
        
    print("\n--- TEAMS ---")
    teams = db.query(Team).all()
    for t in teams:
        print(f"ID: {t.id} | Name: {t.team_name} | Code: {t.team_code} | Department ID: {t.department_id}")
finally:
    db.close()
