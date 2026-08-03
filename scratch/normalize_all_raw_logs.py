import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.database.session import SessionLocal
from app.models.biometric.bm_raw_log import BmRawLog
from app.models.biometric.bm_normalized_log import BmNormalizedLog
from app.services.biometric.normalization_service import NormalizationService

db = SessionLocal()

raw_ids = [r.id for r in db.query(BmRawLog.id).all()]
print(f"Normalizing {len(raw_ids)} raw logs...")

service = NormalizationService(db)
res = service.batch_normalize(raw_ids)

print(f"Normalized: {res.normalized}")
print(f"Skipped: {res.skipped}")
print(f"Errors: {res.errors}")

norm_count = db.query(BmNormalizedLog).count()
print(f"Total BmNormalizedLog records in DB now: {norm_count}")

db.close()
