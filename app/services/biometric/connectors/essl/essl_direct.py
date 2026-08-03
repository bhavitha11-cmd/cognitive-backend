"""
eSSL Direct Device Connector (TCP/IP Socket Protocol)

Connects to eSSL biometric devices using the ZKTeco/eSSL binary protocol
over TCP/IP. Compatible with: E9, E990, SilkBio-900TD, Faceteco, etc.
"""
import socket
import struct
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import time

from app.services.biometric.connectors.base import BiometricConnector, DeviceInfo, RawAttendanceRecord

logger = logging.getLogger(__name__)

# eSSL/ZKTeco protocol constants
CMD_CONNECT = 1000
CMD_EXIT = 1001
CMD_GET_ATTLOG = 13
CMD_GET_USERINFO = 11
CMD_GET_DEVICE_INFO = 11
SESSION_ID = 0
REPLY_OK = 2000
REPLY_ERROR = 2001

class ESSLDirectConnector(BiometricConnector):
    """
    eSSL biometric device connector via direct TCP/IP socket.
    Uses the ZKTeco binary protocol for communication.
    """
    
    def __init__(self, config: dict):
        self.ip_address: str = config.get("ip_address", "")
        self.port: int = config.get("port", 4370)
        self.password: str = config.get("password", "")
        self.timeout: int = config.get("timeout_seconds", 10)
        self._socket: Optional[socket.socket] = None
        self._session_id: int = 0
        self._reply_id: int = 0
    
    def _connect_socket(self) -> None:
        """Establish TCP connection to device."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.ip_address, self.port))
            logger.info(f"[eSSL] Connected to {self.ip_address}:{self.port}")
        except socket.timeout:
            raise ConnectionError(f"Connection timeout to {self.ip_address}:{self.port} after {self.timeout}s")
        except socket.error as e:
            raise ConnectionError(f"Failed to connect to {self.ip_address}:{self.port}: {e}")
    
    def _send_command(self, command: int, data: bytes = b"") -> bytes:
        """Send command packet and receive response."""
        if not self._socket:
            raise ConnectionError("Not connected")
        
        # Build packet: header(2) + size(2) + session_id(2) + reply_id(2) + command(2) + checksum(2) + data
        self._reply_id += 1
        packet = struct.pack(
            "<HHHHHH",
            0x0050,  # Magic header
            8 + len(data),
            self._session_id,
            self._reply_id,
            command,
            0,  # checksum placeholder
        ) + data
        
        try:
            self._socket.send(packet)
            response = self._socket.recv(1024)
            return response
        except socket.timeout:
            raise ConnectionError("Device did not respond in time")
        except socket.error as e:
            raise ConnectionError(f"Communication error: {e}")
    
    def _parse_attendance_record(self, record_bytes: bytes) -> Optional[RawAttendanceRecord]:
        """Parse a single 40-byte attendance record from eSSL binary format."""
        if len(record_bytes) < 40:
            return None
        try:
            user_id_bytes = record_bytes[0:9].rstrip(b'\x00')
            user_id = user_id_bytes.decode('ascii', errors='replace').strip()
            
            second = record_bytes[26]
            minute = record_bytes[25]
            hour = record_bytes[24]
            day = record_bytes[23]
            month = record_bytes[22]
            year = record_bytes[21] + 2000
            
            try:
                punch_dt = datetime(year, month, day, hour, minute, second)
            except ValueError:
                return None
            
            # Punch status: 0=IN, 1=OUT, 4=BREAK_OUT, 5=BREAK_IN
            punch_status = record_bytes[29] if len(record_bytes) > 29 else 0
            verify_type_code = record_bytes[28] if len(record_bytes) > 28 else 1
            
            punch_type_map = {0: "IN", 1: "OUT", 4: "OUT", 5: "IN"}
            verify_type_map = {0: "FP", 1: "FP", 2: "CARD", 3: "PIN", 6: "FACE", 7: "PALM"}
            
            return RawAttendanceRecord(
                device_user_id=user_id,
                punch_timestamp=punch_dt,
                verification_type=verify_type_map.get(verify_type_code, "UNKNOWN"),
                punch_type=punch_type_map.get(punch_status, "UNKNOWN"),
                raw_data={
                    "user_id": user_id,
                    "punch_status": punch_status,
                    "verify_type": verify_type_code,
                    "raw_bytes": record_bytes.hex(),
                }
            )
        except Exception as e:
            logger.warning(f"[eSSL] Failed to parse attendance record: {e}")
            return None
    
    def test_connection(self) -> DeviceInfo:
        """Test connection and return device information."""
        start = time.time()
        self._connect_socket()
        
        try:
            # Send connect command
            response = self._send_command(CMD_CONNECT)
            if len(response) < 8:
                raise ConnectionError("Invalid response from device")
            
            # Extract session ID from response
            self._session_id = struct.unpack_from('<H', response, 4)[0]
            
            response_ms = (time.time() - start) * 1000
            
            # Get device info - in real implementation, send proper info commands
            # For now, return a valid DeviceInfo with available data
            return DeviceInfo(
                model="eSSL Device",
                firmware_version="Unknown",
                device_time=datetime.now(),
                registered_users=0,
                last_attendance_time=None,
                response_time_ms=round(response_ms, 2),
            )
        except Exception as e:
            raise ConnectionError(f"eSSL connection test failed: {e}")
    
    def fetch_attendance(
        self,
        from_dt: datetime,
        to_dt: datetime,
        last_id: Optional[str] = None,
    ) -> list[RawAttendanceRecord]:
        """Fetch attendance records for the specified period."""
        if not self._socket:
            self._connect_socket()
        
        records = []
        try:
            # Request attendance log
            response = self._send_command(CMD_GET_ATTLOG)
            
            # Parse binary response into records
            # Each attendance record is 40 bytes
            record_size = 40
            if len(response) > 16:
                data_portion = response[8:]  # Skip header
                for i in range(0, len(data_portion) - record_size + 1, record_size):
                    record_bytes = data_portion[i:i + record_size]
                    record = self._parse_attendance_record(record_bytes)
                    if record and from_dt <= record.punch_timestamp <= to_dt:
                        records.append(record)
            
            logger.info(f"[eSSL] Fetched {len(records)} attendance records from {self.ip_address}")
        except Exception as e:
            logger.error(f"[eSSL] Failed to fetch attendance: {e}")
            raise
        
        return records
    
    def get_registered_users(self) -> list[dict]:
        """Return list of registered users on the device."""
        if not self._socket:
            self._connect_socket()
        
        users = []
        try:
            response = self._send_command(CMD_GET_USERINFO)
            # Parse user records - each user record has ID and name fields
            if len(response) > 16:
                # Simplified user parsing
                data = response[8:]
                user_size = 72  # Standard eSSL user record size
                for i in range(0, len(data) - user_size + 1, user_size):
                    user_bytes = data[i:i + user_size]
                    user_id = user_bytes[0:9].rstrip(b'\x00').decode('ascii', errors='replace').strip()
                    name = user_bytes[9:33].rstrip(b'\x00').decode('utf-8', errors='replace').strip()
                    if user_id:
                        users.append({"user_id": user_id, "name": name})
        except Exception as e:
            logger.warning(f"[eSSL] Failed to get registered users: {e}")
        
        return users
    
    def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._socket:
            try:
                self._send_command(CMD_EXIT)
            except Exception:
                pass
            finally:
                self._socket.close()
                self._socket = None
                logger.info(f"[eSSL] Disconnected from {self.ip_address}")
