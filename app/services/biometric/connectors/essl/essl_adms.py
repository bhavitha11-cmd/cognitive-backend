"""
eSSL ADMS (Automatic Device Management System) Connector
"""
import logging
from datetime import datetime
from typing import Optional

from app.services.biometric.connectors.base import BiometricConnector, DeviceInfo, RawAttendanceRecord

logger = logging.getLogger(__name__)

class ESSLAdmsConnector(BiometricConnector):
    """
    Acts as a handler for ADMS pushed records.
    Normally, endpoints in the FastAPI app will receive the POST requests
    and pass the payload to this connector for parsing.
    """
    def __init__(self, config: dict):
        self.device_id = config.get("device_id", "Unknown")

    def test_connection(self) -> DeviceInfo:
        # Passive connector, simply returns mock/active state
        return DeviceInfo(
            model="eSSL ADMS",
            firmware_version="N/A",
            device_time=datetime.now(),
            registered_users=0,
            last_attendance_time=None,
            response_time_ms=0,
        )

    def fetch_attendance(
        self,
        from_dt: datetime,
        to_dt: datetime,
        last_id: Optional[str] = None,
    ) -> list[RawAttendanceRecord]:
        # ADMS pushes data, so fetch is generally a no-op or fetches from an intermediate cache
        return []
        
    def parse_payload(self, raw_text: str) -> list[RawAttendanceRecord]:
        """Parses the raw text body from ADMS push."""
        records = []
        lines = raw_text.strip().split('\n')
        for line in lines:
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) >= 4:
                user_id = parts[0]
                timestamp_str = parts[1]
                punch_state = parts[2]
                verify_type = parts[3]
                
                try:
                    punch_ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    
                    punch_type_map = {'0': "IN", '1': "OUT"}
                    verify_map = {'1': "FP", '2': "CARD"}
                    
                    records.append(RawAttendanceRecord(
                        device_user_id=user_id,
                        punch_timestamp=punch_ts,
                        verification_type=verify_map.get(verify_type, "UNKNOWN"),
                        punch_type=punch_type_map.get(punch_state, "UNKNOWN"),
                        raw_data={"raw_line": line}
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse ADMS line {line}: {e}")
        return records

    def get_registered_users(self) -> list[dict]:
        return []

    def disconnect(self) -> None:
        pass
