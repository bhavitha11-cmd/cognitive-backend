"""
eSSL REST API Connector
"""
import logging
from datetime import datetime
from typing import Optional
import requests

from app.services.biometric.connectors.base import BiometricConnector, DeviceInfo, RawAttendanceRecord

logger = logging.getLogger(__name__)

class ESSLRestConnector(BiometricConnector):
    def __init__(self, config: dict):
        self.base_url = config.get("base_url")
        self.token = config.get("token")
        self.username = config.get("username")
        self.password = config.get("password")
        self.timeout = config.get("timeout", 10)
        self.session = requests.Session()
        
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        elif self.username and self.password:
            self.session.auth = (self.username, self.password)

    def test_connection(self) -> DeviceInfo:
        try:
            start = datetime.now()
            resp = self.session.get(f"{self.base_url}/info", timeout=self.timeout)
            resp.raise_for_status()
            response_ms = (datetime.now() - start).total_seconds() * 1000
            
            data = resp.json()
            return DeviceInfo(
                model=data.get("model", "eSSL REST"),
                firmware_version=data.get("firmware", "Unknown"),
                device_time=datetime.now(),
                registered_users=data.get("user_count", 0),
                last_attendance_time=None,
                response_time_ms=response_ms,
            )
        except Exception as e:
            raise ConnectionError(f"REST API connection failed: {e}")

    def fetch_attendance(
        self,
        from_dt: datetime,
        to_dt: datetime,
        last_id: Optional[str] = None,
    ) -> list[RawAttendanceRecord]:
        records = []
        try:
            params = {
                "start_time": from_dt.isoformat(),
                "end_time": to_dt.isoformat()
            }
            resp = self.session.get(f"{self.base_url}/transactions", params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            
            for item in data.get("data", []):
                punch_ts = datetime.fromisoformat(item.get("punch_time"))
                records.append(RawAttendanceRecord(
                    device_user_id=str(item.get("emp_id")),
                    punch_timestamp=punch_ts,
                    verification_type=item.get("verify_type", "UNKNOWN"),
                    punch_type=item.get("punch_type", "UNKNOWN"),
                    raw_data=item
                ))
            logger.info(f"[eSSL REST] Fetched {len(records)} records.")
        except Exception as e:
            logger.error(f"Error fetching from REST API: {e}")
            raise
        return records

    def get_registered_users(self) -> list[dict]:
        try:
            resp = self.session.get(f"{self.base_url}/users", timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return [{"user_id": str(u.get("emp_id")), "name": u.get("name")} for u in data.get("data", [])]
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []

    def disconnect(self) -> None:
        self.session.close()
