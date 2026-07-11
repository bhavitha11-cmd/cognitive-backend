import sys
import os
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.approval import ApprovalWorkflowStep, ApprovalWorkflow
from app.services.approval_service import ApprovalService

def main():
    db = SessionLocal()
    try:
        service = ApprovalService(db)
        
        # 1. Fetch all steps
        steps = db.query(ApprovalWorkflowStep).all()
        print(f"Found {len(steps)} steps total in DB.")
        
        # Group by workflow_id and requester_role_id
        grouped = {}
        for s in steps:
            key = (s.workflow_id, s.requester_role_id)
            grouped.setdefault(key, []).append(s)
            
        # 2. Normalize each group
        print("Normalizing levels...")
        for (wf_id, role_id), group_steps in grouped.items():
            group_steps.sort(key=lambda x: x.level)
            for idx, s in enumerate(group_steps, start=1):
                if s.level != idx:
                    print(f"Updating step {s.id} (Workflow: {wf_id}, Role: {role_id}) from level {s.level} to {idx}")
                    s.level = idx
                    
        db.commit()
        print("Database commit successful!")
        
        # 3. Test activating workflow c61f337c-92a4-40ea-87b8-ad3f775bf839
        wf_id = uuid.UUID("c61f337c-92a4-40ea-87b8-ad3f775bf839")
        print(f"Attempting to activate workflow {wf_id}...")
        wf = service.activate_workflow(wf_id)
        print(f"SUCCESS: Workflow '{wf.name}' version {wf.version} activated successfully!")
        
    except Exception as e:
        db.rollback()
        print("Error during execution, rolled back:", e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
