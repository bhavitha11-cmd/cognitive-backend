import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.models.biometric.bm_employee_mapping import BmEmployeeMapping
from app.models.employee import Employee

db = SessionLocal()

mappings = db.query(BmEmployeeMapping).all()
print(f"Total Employee Mappings: {len(mappings)}")
print("Sample Mappings (Biometric User ID -> Employee Name):")
for m in mappings[:15]:
    emp = db.query(Employee).filter(Employee.id == m.employee_id).first()
    emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
    emp_code = emp.employee_code if emp else "-"
    print(f"  Device User ID: '{m.biometric_user_id:<10}' ---> Mapped Employee: '{emp_name}' ({emp_code})")

db.close()
