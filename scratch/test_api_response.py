import sys; sys.path.insert(0, '.')
from app.database.session import SessionLocal
from app.services.biometric.biometric_log_service import BiometricLogService

db = SessionLocal()
svc = BiometricLogService(db)
logs, total = svc.list_normalized_logs({}, page=1, page_size=5)
print(f'Total: {total}')
for log in logs:
    ename = log.get("employee_name")
    dname = log.get("device_name")
    ecode = log.get("employee_code")
    print(f"  employee_name={ename!r}, device_name={dname!r}, emp_code={ecode!r}")
db.close()
