import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.project import Project
from app.services.project_metrics_service import ProjectMetricsService

def main():
    db = SessionLocal()
    try:
        parts = db.query(Project).filter(Project.is_active == True).all()
        print(f"Found {len(parts)} active parts to recalculate.")
        for part in parts:
            print(f"Recalculating part {part.project_code} ({part.part_name})...")
            res = ProjectMetricsService.recalculate(db, part.id)
            print(f"  Result: {res}")
        db.commit()
        print("All parts recalculated and changes committed successfully!")
    except Exception as e:
        db.rollback()
        print("Error occurred, transaction rolled back:", e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
