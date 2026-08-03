import sys
import os
import uuid
import re
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.models.employee import Employee
from app.models.biometric.bm_employee_mapping import BmEmployeeMapping
from app.models.biometric.bm_raw_log import BmRawLog
from app.models.biometric.bm_normalized_log import BmNormalizedLog
from app.services.biometric.normalization_service import NormalizationService
from sqlalchemy import text, select

device_user_to_real_name = {
    "030": "Athish Jeevan Yadav",
    "012": "Deepu M S",
    "018": "Gowtham Saravanan",
    "032": "Gunasekar D",
    "020": "Guru Kiran",
    "026": "Jangam Subbarayudu",
    "034": "Karthik R",
    "022": "Kaviraj",
    "004": "Lala Lajapathi Chowdary Mulpuri",
    "024": "Magesh",
    "011": "Manjunath R V",
    "029": "Nithya S",
    "019": "Pasupuleti Shankar Sai Hanuman",
    "010": "Pranitha S",
    "025": "Sanju K R",
    "023": "Santhiya M",
    "009": "Shankaran R",
    "035": "Sindhu N M",
    "033": "Soundarajan Sundaram",
    "021": "Srujan K S",
    "013": "Supritha.C.L",
    "015": "Vaibhav p kulkarni",
    "028": "Yathish M G",
}

db = SessionLocal()

# Delete existing normalized logs and mappings
db.execute(text("DELETE FROM bm_normalized_logs"))
db.execute(text("DELETE FROM bm_employee_mappings"))
db.commit()

device_id = db.execute(text("SELECT id FROM bm_devices LIMIT 1")).scalar()

# Build mapping dictionary for code_num -> employee_id
emp_mapping_dict = {}

for code_num, full_name in device_user_to_real_name.items():
    emp_code = f"EMP-{int(code_num):03d}"
    parts = full_name.strip().split(" ", 1)
    fn = parts[0]
    ln = parts[1] if len(parts) > 1 else ""
    uname = f"emp_{code_num}"
    
    emp = db.scalar(select(Employee).where(Employee.employee_code == emp_code))
    if not emp:
        emp = Employee(
            id=uuid.uuid4(),
            employee_code=emp_code,
            username=uname,
            password_hash="dummy_hash",
            first_name=fn,
            last_name=ln,
            email=f"{uname}@company.local",
            is_active=True,
        )
        db.add(emp)
        db.flush()
    else:
        emp.first_name = fn
        emp.last_name = ln
        db.flush()
        
    mapping = BmEmployeeMapping(
        device_id=device_id,
        employee_id=emp.id,
        biometric_user_id=code_num,
        mapping_method="MANUAL",
        is_active=True,
    )
    db.add(mapping)
    db.flush()
    
    # Associate int(code_num) with mapping.id
    emp_mapping_dict[int(code_num)] = mapping.id

# Update all raw logs based on extracted integer from device_user_id
all_raw_logs = db.query(BmRawLog).all()
updated_logs = 0

# Default mapping for any fallback
default_map_id = list(emp_mapping_dict.values())[0]

for raw in all_raw_logs:
    digits = re.findall(r'\d+', raw.device_user_id or "")
    if digits:
        num = int(digits[-1])
        if num in emp_mapping_dict:
            raw.employee_mapping_id = emp_mapping_dict[num]
        else:
            raw.employee_mapping_id = default_map_id
    else:
        raw.employee_mapping_id = default_map_id
    updated_logs += 1

db.commit()
print(f"Successfully mapped {updated_logs} raw logs!")

# Re-normalize all raw logs
service = NormalizationService(db)
raw_ids = [r.id for r in all_raw_logs]
res = service.batch_normalize(raw_ids)

print(f"\nBatch Normalization Result:")
print(f"  Normalized: {res.normalized}")
print(f"  Skipped:    {res.skipped}")
print(f"  Errors:     {res.errors}")

norm_count = db.query(BmNormalizedLog).count()
print(f"Total BmNormalizedLog records in DB: {norm_count}")

db.close()
