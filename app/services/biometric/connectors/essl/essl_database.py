"""
eSSL Database Connector

Reads attendance records directly from the database used by eSSL software
(such as eTimeTrackLite).
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, text
from app.services.biometric.connectors.base import BiometricConnector, DeviceInfo, RawAttendanceRecord

logger = logging.getLogger(__name__)

class ESSLDatabaseConnector(BiometricConnector):
    def __init__(self, config: dict):
        self.db_url = config.get("db_url")
        if not self.db_url:
            raise ValueError("db_url is required for database connector")
        self.engine = create_engine(self.db_url)
        self.device_id = config.get("device_id", "Unknown")

    def test_connection(self) -> DeviceInfo:
        start = datetime.now()
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            response_ms = (datetime.now() - start).total_seconds() * 1000
            return DeviceInfo(
                model="eSSL DB",
                firmware_version="N/A",
                device_time=datetime.now(),
                registered_users=0,
                last_attendance_time=None,
                response_time_ms=response_ms,
            )
        except Exception as e:
            raise ConnectionError(f"Database connection failed: {e}")

    def fetch_attendance(
        self,
        from_dt: datetime,
        to_dt: datetime,
        last_id: Optional[str] = None,
    ) -> list[RawAttendanceRecord]:
        records = []
        try:
            with self.engine.connect() as conn:
                # Assuming standard eTimeTrackLite table structure 'AttendanceLogs' or 'iclock_transaction'
                query = text("""
                    SELECT emp_id, punch_time, punch_state, verify_type
                    FROM iclock_transaction
                    WHERE punch_time >= :from_dt AND punch_time <= :to_dt
                """)
                result = conn.execute(query, {"from_dt": from_dt, "to_dt": to_dt})
                for row in result:
                    # Mapping based on standard defaults
                    punch_state = row._mapping.get('punch_state', '0')
                    verify_type = row._mapping.get('verify_type', '1')
                    
                    punch_type_map = {'0': "IN", '1': "OUT"}
                    verify_type_map = {'1': "FP", '2': "CARD"}
                    
                    records.append(RawAttendanceRecord(
                        device_user_id=str(row._mapping.get('emp_id')),
                        punch_timestamp=row._mapping.get('punch_time'),
                        verification_type=verify_type_map.get(str(verify_type), "UNKNOWN"),
                        punch_type=punch_type_map.get(str(punch_state), "UNKNOWN"),
                        raw_data=dict(row._mapping)
                    ))
            logger.info(f"[eSSL DB] Fetched {len(records)} records.")
        except Exception as e:
            logger.error(f"Error fetching from DB: {e}")
            raise
        return records

    def get_registered_users(self) -> list[dict]:
        return []

    def disconnect(self) -> None:
        self.engine.dispose()
