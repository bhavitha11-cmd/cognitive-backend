import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from datetime import date, datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.missed_clockin_request import MissedClockinRequest
from app.models.employee import Employee

def test_real_db_storage():
    print(f"Connecting to database at: {settings.DATABASE_URL.split('@')[-1]}")
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Get an existing employee from the DB to associate with the request
        emp = db.query(Employee).first()
        if not emp:
            print("No employee found in the database. Cannot run database storage test.")
            return
        
        print(f"Found employee: {emp.first_name} {emp.last_name} (ID: {emp.id})")
        
        # Create a test MissedClockinRequest
        test_request = MissedClockinRequest(
            id=uuid.uuid4(),
            employee_id=emp.id,
            attendance_date=date(2026, 7, 9),
            requested_clock_in=datetime.now(timezone.utc),
            reason="Integration test for DB storage",
            status="PENDING"
        )
        
        # Save to DB
        db.add(test_request)
        db.commit()
        print(f"Test request created with ID: {test_request.id} and committed successfully.")
        
        # Retrieve from DB
        retrieved = db.query(MissedClockinRequest).filter(MissedClockinRequest.id == test_request.id).first()
        assert retrieved is not None
        assert retrieved.employee_id == emp.id
        assert retrieved.reason == "Integration test for DB storage"
        assert retrieved.status == "PENDING"
        print(f"Retrieved request from DB successfully. All fields matched: reason='{retrieved.reason}', status='{retrieved.status}'.")
        
        # Clean up
        db.delete(retrieved)
        db.commit()
        print("Cleaned up database: test record deleted successfully.")
        print("Database storage verification: PASSED.")
        
    except Exception as e:
        db.rollback()
        print(f"Database storage verification FAILED with error: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    test_real_db_storage()
