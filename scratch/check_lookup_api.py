import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.services.employee_service import EmployeeService

def main():
    db = SessionLocal()
    try:
        service = EmployeeService(db)
        items = service.get_lookup()
        print("--- Employee Lookup API Result ---")
        print("Total items:", len(items))
        for item in items:
            print(item.model_dump())
    finally:
        db.close()

if __name__ == "__main__":
    main()
