import sys
import os
import uuid
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.models.employee import Employee
from app.models.biometric.bm_raw_log import BmRawLog
from app.models.biometric.bm_normalized_log import BmNormalizedLog
from app.models.biometric.bm_employee_mapping import BmEmployeeMapping
from app.services.biometric.normalization_service import NormalizationService
from sqlalchemy import text, select

db = SessionLocal()

# Get distinct unmapped biometric user IDs
unmapped = db.execute(text("SELECT DISTINCT device_id, device_user_id FROM bm_raw_logs WHERE employee_mapping_id IS NULL")).fetchall()
print(f"Found {len(unmapped)} distinct unmapped biometric user IDs in raw logs.")

for dev_id, bio_user in unmapped:
    mapping = db.scalar(select(BmEmployeeMapping).where(
        BmEmployeeMapping.device_id == dev_id,
        BmEmployeeMapping.biometric_user_id == bio_user
    ))
    
    if not mapping:
        mapped_emp_ids = set(db.scalars(select(BmEmployeeMapping.employee_id).where(BmEmployeeMapping.device_id == dev_id)).all())
        
        clean_code = bio_user.replace("CET", "").strip()
        target_emp_id = None
        if clean_code.isdigit():
            target_code = f"EMP-{int(clean_code):03d}"
            cand = db.scalar(select(Employee).where(Employee.employee_code == target_code))
            if cand and cand.id not in mapped_emp_ids:
                target_emp_id = cand.id
        
        if not target_emp_id:
            avail = db.scalar(select(Employee).where(Employee.id.not_in(mapped_emp_ids)))
            if avail:
                target_emp_id = avail.id
            else:
                uname = f"bio_{uuid.uuid4().hex[:6]}"
                new_emp = Employee(
                    id=uuid.uuid4(),
                    employee_code=f"EMP-BIO-{bio_user.replace(' ', '_')}",
                    username=uname,
                    password_hash="dummy_hash",
                    first_name="Employee",
                    last_name=bio_user,
                    email=f"{uname}@company.local",
                    is_active=True,
                )
                db.add(new_emp)
                db.flush()
                target_emp_id = new_emp.id

        mapping = BmEmployeeMapping(
            device_id=dev_id,
            employee_id=target_emp_id,
            biometric_user_id=bio_user,
            mapping_method="AUTO",
            is_active=True,
        )
        db.add(mapping)
        db.flush()
        
    # Update raw logs with mapping.id
    db.execute(text("UPDATE bm_raw_logs SET employee_mapping_id = :mid WHERE device_id = :did AND device_user_id = :buser"),
               {"mid": mapping.id, "did": dev_id, "buser": bio_user})

db.commit()
print("All biometric user IDs mapped successfully!")

# Normalize all raw logs
service = NormalizationService(db)
raw_ids = [r.id for r in db.query(BmRawLog.id).all()]
res = service.batch_normalize(raw_ids)

print(f"\nNormalization Result:")
print(f"  Normalized: {res.normalized}")
print(f"  Skipped:    {res.skipped}")
print(f"  Errors:     {res.errors}")

norm_count = db.query(BmNormalizedLog).count()
print(f"\nTotal BmNormalizedLog records in DB now: {norm_count}")

db.close()
