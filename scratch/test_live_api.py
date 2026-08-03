"""
Direct HTTP API diagnostic - calls the live running backend
to see EXACTLY what JSON the API returns.
"""
import requests
import json

BASE = "http://localhost:8000/api/v1"

# 1. Login as admin
login_resp = requests.post(f"{BASE}/auth/login", json={
    "username": "admin",
    "password": "Admin@1234"
})
print(f"Login status: {login_resp.status_code}")

if login_resp.status_code != 200:
    # try alternate password
    login_resp = requests.post(f"{BASE}/auth/login", json={
        "username": "admin", 
        "password": "Admin@123"
    })
    print(f"Login status (alt): {login_resp.status_code}")

if login_resp.status_code != 200:
    print(f"Login response: {login_resp.text[:500]}")
    
    # Try to find admin user in db directly
    import sys; sys.path.insert(0, '.')
    from app.database.session import SessionLocal
    from app.models.employee import Employee
    from sqlalchemy import select
    db = SessionLocal()
    admins = db.scalars(select(Employee).where(Employee.employee_code == "EMP-001")).all()
    for a in admins:
        print(f"Admin found: {a.username}, email={a.email}, code={a.employee_code}")
    db.close()
    exit(1)

token = login_resp.json().get("access_token") or login_resp.json().get("data", {}).get("access_token")
print(f"Token obtained: {token[:40]}..." if token else "NO TOKEN!")

if not token:
    print(f"Full response: {json.dumps(login_resp.json(), indent=2)[:500]}")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# 2. Call biometric logs API
logs_resp = requests.get(f"{BASE}/biometric/logs", params={"page": 1, "page_size": 5}, headers=headers)
print(f"\nBiometric Logs API status: {logs_resp.status_code}")

if logs_resp.status_code == 200:
    data = logs_resp.json()
    logs = data.get("data", {}).get("logs", [])
    total = data.get("data", {}).get("total", 0)
    print(f"Total records: {total}")
    print(f"\nFirst 3 records from LIVE API:")
    for log in logs[:3]:
        print(f"  employee_name  = {log.get('employee_name')!r}")
        print(f"  employee_code  = {log.get('employee_code')!r}")
        print(f"  employee_id    = {log.get('employee_id')!r}")
        print(f"  device_name    = {log.get('device_name')!r}")
        print(f"  device_id      = {log.get('device_id')!r}")
        print()
else:
    print(f"Error: {logs_resp.text[:500]}")

# 3. Call live attendance API
live_resp = requests.get(f"{BASE}/biometric/live", headers=headers)
print(f"\nLive Attendance API status: {live_resp.status_code}")
if live_resp.status_code == 200:
    data = live_resp.json()
    print(f"Live records count: {len(data) if isinstance(data, list) else 'not a list'}")
    if isinstance(data, list) and data:
        for r in data[:3]:
            print(f"  {r}")
    else:
        print("  No live records (expected - device clock shows year 2000, no punches today)")
else:
    print(f"Error: {live_resp.text[:500]}")
