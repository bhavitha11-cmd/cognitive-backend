import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()

emp_count = db.execute(text("SELECT count(*) FROM employees")).scalar()
print(f"Total employees in database: {emp_count}")

employees = db.execute(text("SELECT id, employee_code, first_name, last_name FROM employees LIMIT 10")).fetchall()
print("Sample employees:")
for emp in employees:
    print(f"  ID: {emp.id} | Code: {emp.employee_code} | Name: {emp.first_name} {emp.last_name}")

db.close()
