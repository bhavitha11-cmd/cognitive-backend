import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.core.seeder import run_authorization_seeder

def main():
    db = SessionLocal()
    try:
        print("Running run_authorization_seeder...")
        run_authorization_seeder(db)
        print("Successfully ran run_authorization_seeder!")
    except Exception as e:
        print(f"Error running seeder: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
