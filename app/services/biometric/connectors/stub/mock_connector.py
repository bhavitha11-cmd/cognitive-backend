"""
Mock Biometric Connector for Testing
"""
from datetime import datetime, timedelta
from typing import Optional

from app.services.biometric.connectors.base import BiometricConnector, DeviceInfo, RawAttendanceRecord

class MockBiometricConnector(BiometricConnector):
    def __init__(self, config: dict):
        self.device_id = config.get("device_id", "MOCK-001")
        self.fail_test = config.get("fail_test", False)
        
    def test_connection(self) -> DeviceInfo:
        if self.fail_test:
            raise ConnectionError("Mock connection failure")
        return DeviceInfo(
            model="Mock Device",
            firmware_version="1.0.0",
            device_time=datetime.now(),
            registered_users=10,
            last_attendance_time=datetime.now(),
            response_time_ms=15.5,
        )
        
    def fetch_attendance(
        self,
        from_dt: datetime,
        to_dt: datetime,
        last_id: Optional[str] = None,
    ) -> list[RawAttendanceRecord]:
        return [
            RawAttendanceRecord(
                device_user_id="1001",
                punch_timestamp=from_dt + timedelta(hours=1),
                verification_type="FP",
                punch_type="IN",
                raw_data={"mock": True}
            )
        ]
        
    def get_registered_users(self) -> list[dict]:
        return [{"user_id": "1001", "name": "Test User"}]
        
    def disconnect(self) -> None:
        pass
