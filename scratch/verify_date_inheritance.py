import sys
import os
import uuid
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.parent_project import ParentProject
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.services.project_metrics_service import ProjectMetricsService

def main():
    db = SessionLocal()
    try:
        # Get a parent project and its parts
        proj = db.query(ParentProject).first()
        if not proj:
            print("No projects found in DB to test with.")
            return
            
        part = db.query(Project).filter(Project.parent_project_id == proj.id).first()
        if not part:
            print(f"Parent project {proj.name} has no parts to test with.")
            return

        print("==================================================")
        print("BEFORE RECALCULATION")
        print(f"Parent Project: {proj.name}")
        print(f"  Planned Start: {proj.planned_start_date}, Planned End: {proj.planned_end_date}")
        print(f"Part: {part.part_name} (Code: {part.project_code})")
        print(f"  Planned Start: {part.planned_start_date}, Planned End: {part.planned_end_date}")
        
        # Get tasks under this part
        tasks = db.query(Task).filter(Task.project_id == part.id, Task.is_active == True).all()
        print(f"Tasks count under part: {len(tasks)}")
        for t in tasks:
            print(f"  Task {t.task_code}: {t.planned_start_date} -> {t.planned_end_date}")

        # If only 1 task, create a temporary second task
        if len(tasks) < 2:
            print("\nCreating a temporary second task for test...")
            team = db.query(Team).first()
            if not team:
                print("No teams found in DB to create task.")
                return
            temp_task = Task(
                task_code=f"{part.project_code}-TEMP-TEST",
                project_id=part.id,
                team_id=team.id,
                title="Temporary Test Task",
                status="NOT_STARTED",
                priority="MEDIUM",
                is_active=True,
                planned_start_date=date(2026, 8, 5),
                planned_end_date=date(2026, 8, 20)
            )
            db.add(temp_task)
            db.flush()
            
            # Re-fetch tasks
            tasks = db.query(Task).filter(Task.project_id == part.id, Task.is_active == True).all()
            print(f"New tasks count under part: {len(tasks)}")

        # Set specific planned dates on the tasks
        print("\nUpdating tasks to specific dates...")
        tasks[0].planned_start_date = date(2026, 8, 1)
        tasks[0].planned_end_date = date(2026, 8, 10)
        
        tasks[1].planned_start_date = date(2026, 8, 5)
        tasks[1].planned_end_date = date(2026, 8, 20)
        db.flush()

        # Recalculate Part
        print("Invoking ProjectMetricsService.recalculate...")
        ProjectMetricsService.recalculate(db, part.id)

        # Refresh objects
        db.refresh(part)
        db.refresh(proj)

        print("\nAFTER RECALCULATION")
        print(f"Part: {part.part_name}")
        print(f"  Expected Start: 2026-08-01, Actual: {part.planned_start_date}")
        print(f"  Expected End: 2026-08-20, Actual: {part.planned_end_date}")
        print(f"Parent Project: {proj.name}")
        print(f"  Expected Start: 2026-08-01, Actual: {proj.planned_start_date}")
        print(f"  Expected End: 2026-08-20, Actual: {proj.planned_end_date}")

        part_ok = part.planned_start_date == date(2026, 8, 1) and part.planned_end_date == date(2026, 8, 20)
        proj_ok = proj.planned_start_date == date(2026, 8, 1) and proj.planned_end_date == date(2026, 8, 20)

        if part_ok:
            print("\nSUCCESS: Part dates recalculated correctly!")
        else:
            print("\nFAILURE: Part dates did not recalculate correctly.")

        if proj_ok:
            print("SUCCESS: Parent Project dates rolled up correctly!")
        else:
            print("FAILURE: Parent Project dates did not roll up correctly.")
            
    finally:
        print("\nRolling back transaction to keep DB clean.")
        db.rollback()
        db.close()

if __name__ == "__main__":
    main()
