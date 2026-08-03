import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.models.biometric.bm_raw_log import BmRawLog
from app.models.biometric.bm_normalized_log import BmNormalizedLog

db = SessionLocal()
raw_count = db.query(BmRawLog).count()
norm_count = db.query(BmNormalizedLog).count()

print(f"Total BmRawLog records in DB: {raw_count}")
print(f"Total BmNormalizedLog records in DB: {norm_count}")

sample_raw = db.query(BmRawLog).limit(10).all()
print("\nSample BmRawLog records in DB:")
for r in sample_raw:
    print(f"  User: {r.device_user_id:<10} | Time: {r.punch_timestamp} | Verification: {r.verification_type} | Punch: {r.punch_type} | Duplicate: {r.is_duplicate}")

db.close()
