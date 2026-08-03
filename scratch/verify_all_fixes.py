import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.services.biometric.biometric_log_service import BiometricLogService
from app.services.biometric.live_attendance_service import LiveAttendanceService
from sqlalchemy import text

db = SessionLocal()

# Test 1: Biometric log service returns correct names
print("=== TEST 1: Biometric Logs API ===")
svc = BiometricLogService(db)
logs, total = svc.list_normalized_logs({}, page=1, page_size=10)
print(f"Total: {total}")
for log in logs:
    name = log.get("employee_name", "MISSING")
    dev = log.get("device_name", "MISSING")
    code = log.get("employee_code", "MISSING")
    print(f"  Name={name!r}, Code={code!r}, Device={dev!r}")

print()
print("=== TEST 2: Live Attendance API ===")
live_svc = LiveAttendanceService(db)
# Simulate getting live attendance (will be empty since punches are from year 2000, not today)
records = live_svc.get_live_attendance()
print(f"Live records for TODAY: {len(records)}")
if records:
    for r in records[:3]:
        print(f"  {r}")
else:
    print("  (No punches today - device clock shows year 2000)")
    print("  Once you scan a finger on the device and sync, it will show here.")

print()
print("=== TEST 3: Sync engine fuzzy mapping ===")
from app.services.biometric.sync_engine import SyncEngine
from sqlalchemy import text as t_
device_id = db.execute(t_("SELECT id FROM bm_devices LIMIT 1")).scalar()
engine = SyncEngine(db)
# Test fuzzy mapping
for test_id in ["030", "CET030", "CET004", "004", "9", "009"]:
    mapping = engine._find_employee_mapping(device_id, test_id)
    if mapping:
        from app.models.employee import Employee
        from sqlalchemy import select
        emp = db.scalar(select(Employee).where(Employee.id == mapping.employee_id))
        emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
        print(f"  '{test_id}' -> {emp_name!r} (biometric_user_id={mapping.biometric_user_id!r})")
    else:
        print(f"  '{test_id}' -> NOT MAPPED")

db.close()
print("\nAll tests completed!")
