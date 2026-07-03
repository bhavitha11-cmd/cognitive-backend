import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.task import Task

db = SessionLocal()
try:
    print("--- TASKS ---")
    tasks = db.query(Task).limit(10).all()
    for t in tasks:
        print(f"ID: {t.id} | Code: {t.task_code} | Title: {t.title} | Dept Cat: {t.department_category} | Team ID: {t.team_id}")
finally:
    db.close()
