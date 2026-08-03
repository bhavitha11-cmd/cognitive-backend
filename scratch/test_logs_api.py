import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.services.biometric.biometric_log_service import BiometricLogService

db = SessionLocal()
svc = BiometricLogService(db)

logs, total = svc.list_normalized_logs(filters={}, page=1, page_size=10)
print(f"Total normalized logs available for UI: {total}")
print("Sample normalized logs:")
for l in logs:
    print(f"  Emp Name: {l['employee_name']:<18} | Code: {l['employee_code']:<12} | Punch Time: {l['punch_timestamp']} | Device: {l['device_name']}")

db.close()
