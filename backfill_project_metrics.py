"""
Backfill script: recalculate project metrics for all existing projects.
Run this ONCE after the migration (add_project_computed_fields) is applied.
Safe to run multiple times — idempotent.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.connection import engine
from app.database.session import SessionLocal
from app.migrations.add_project_computed_fields import upgrade
from app.models.project import Project
from app.services.project_metrics_service import ProjectMetricsService
from sqlalchemy import select

def run():
    print("=" * 60)
    print("STEP 1: Running migration (add actual_hours, progress)...")
    upgrade(engine)

    print("\nSTEP 2: Backfilling project metrics for all existing projects...")
    db = SessionLocal()
    try:
        projects = db.scalars(select(Project).where(Project.is_active == True)).all()
        print(f"  Found {len(projects)} active project(s).\n")

        for i, project in enumerate(projects, 1):
            try:
                result = ProjectMetricsService.recalculate(db, project.id)
                db.commit()
                nv = result.get("new", {})
                print(
                    f"  [{i}/{len(projects)}] {project.project_code} | "
                    f"est={nv.get('estimated_hours', 0):.1f}h "
                    f"act={nv.get('actual_hours', 0):.1f}h "
                    f"prog={nv.get('progress', 0):.1f}% "
                    f"status={nv.get('status', '?')}"
                )
            except Exception as e:
                db.rollback()
                print(f"  [{i}/{len(projects)}] ERROR for {project.project_code}: {e}")

        print("\nBackfill complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
