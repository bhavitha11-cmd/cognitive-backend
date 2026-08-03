"""
Biometric Connector Abstract Base

This module defines the contract that all vendor connectors must implement.
Adding a new vendor = create one new file implementing BiometricConnector.
No changes required anywhere else in the codebase.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class DeviceInfo:
    """Normalized device info returned by test_connection."""
    model: str
    firmware_version: str
    device_time: datetime
    registered_users: int
    last_attendance_time: Optional[datetime]
    response_time_ms: float

@dataclass
class RawAttendanceRecord:
    """A single attendance punch record from the device."""
    device_user_id: str
    punch_timestamp: datetime
    verification_type: str   # FP, CARD, PIN, FACE, PALM
    punch_type: str          # IN, OUT, UNKNOWN
    raw_data: dict[str, Any] = field(default_factory=dict)

class BiometricConnector(ABC):
    """
    Abstract base class for all biometric device connectors.
    
    Each vendor connector must implement this interface.
    The architecture guarantees that no other module needs to change
    when a new vendor connector is added.
    """
    
    @abstractmethod
    def test_connection(self) -> DeviceInfo:
        """Test connectivity and return device metadata."""
        ...
    
    @abstractmethod
    def fetch_attendance(
        self,
        from_dt: datetime,
        to_dt: datetime,
        last_id: Optional[str] = None,
    ) -> list[RawAttendanceRecord]:
        """Fetch attendance records within the given datetime range."""
        ...
    
    @abstractmethod
    def get_registered_users(self) -> list[dict]:
        """Return list of users registered on the device."""
        ...
    
    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connection resources."""
        ...
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.disconnect()
        except Exception as e:
            logger.warning(f"Error during connector disconnect: {e}")
        return False
