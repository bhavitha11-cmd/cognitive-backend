import sys, os, uuid, re
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.models.employee import Employee
from app.models.biometric.bm_employee_mapping import BmEmployeeMapping
from sqlalchemy import select, text

# The exact mapping table from the physical device
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

device_id = db.execute(text("SELECT id FROM bm_devices LIMIT 1")).scalar()
print(f"Device ID: {device_id}")

# Get all existing mappings so we know what's already there
existing_mappings = db.scalars(
    select(BmEmployeeMapping).where(BmEmployeeMapping.device_id == device_id)
).all()
existing_by_user_id = {m.biometric_user_id: m for m in existing_mappings}
print(f"Existing mappings: {len(existing_mappings)}")
print("Existing biometric_user_ids:", list(existing_by_user_id.keys()))

# For each employee, also add a CETxxx mapping that points to the same employee
added = 0
for code_num, full_name in device_user_to_real_name.items():
    cet_key = f"CET{code_num}"  # e.g., CET030
    
    # Get the existing mapping for plain number e.g. '030'
    base_mapping = existing_by_user_id.get(code_num)
    if not base_mapping:
        print(f"  WARNING: No mapping for code {code_num!r}, skipping CET variant")
        continue
    
    emp_id = base_mapping.employee_id
    
    # Check if CET variant mapping already exists
    if cet_key in existing_by_user_id:
        # Update its employee_id to match the base mapping
        cet_m = existing_by_user_id[cet_key]
        if cet_m.employee_id != emp_id:
            print(f"  FIXING: CET{code_num} was mapped to wrong employee, correcting...")
            db.execute(text("DELETE FROM bm_employee_mappings WHERE id = :id"), {"id": cet_m.id})
            db.flush()
            new_m = BmEmployeeMapping(
                device_id=device_id,
                employee_id=emp_id,
                biometric_user_id=cet_key,
                mapping_method="MANUAL",
                is_active=True,
            )
            db.add(new_m)
            db.flush()
            added += 1
        else:
            print(f"  OK: {cet_key!r} already mapped correctly to {full_name}")
    else:
        # Create new CET variant mapping
        new_m = BmEmployeeMapping(
            device_id=device_id,
            employee_id=emp_id,
            biometric_user_id=cet_key,
            mapping_method="MANUAL",
            is_active=True,
        )
        db.add(new_m)
        db.flush()
        print(f"  ADDED: {cet_key!r} -> {full_name}")
        added += 1

db.commit()
print(f"\nDone! Added/fixed {added} CET-prefixed mappings.")

# Verify
total_mappings = db.scalar(text("SELECT count(*) FROM bm_employee_mappings"))
print(f"Total mappings now: {total_mappings}")

db.close()
