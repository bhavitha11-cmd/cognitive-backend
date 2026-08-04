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

def _calc_zk_checksum(data: bytes) -> int:
    """Calculate ZK protocol 16-bit 1's complement checksum."""
    length = len(data)
    checksum = 0
    i = 0
    while i < length:
        if i + 1 < length:
            val = struct.unpack('<H', data[i:i+2])[0]
        else:
            val = data[i]
        checksum += val
        if checksum > 0xFFFF:
            checksum = (checksum & 0xFFFF) + 1
        i += 2
    checksum = (~checksum) & 0xFFFF
    return checksum

class ESSLDirectConnector(BiometricConnector):
    """
    eSSL/ZKTeco biometric device connector via UDP or TCP socket protocol.
    Supports ZKTeco binary protocol over UDP (default) & TCP socket.
    """
    
    def __init__(self, config: dict):
        self.ip_address: str = config.get("ip_address", "")
        self.port: int = config.get("port", 4370)
        self.password: str = str(config.get("password", "") or "")
        self.timeout: int = config.get("timeout_seconds", 10)
        self.use_tcp: bool = config.get("use_tcp", False)
        self._socket: Optional[socket.socket] = None
        self._session_id: int = 0
        self._reply_id: int = 0
        self._is_udp: bool = not self.use_tcp
    
    def _connect_socket(self) -> None:
        """Establish UDP or TCP socket connection to device."""
        if self._is_udp:
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.settimeout(self.timeout)
                logger.info(f"[eSSL/ZK] Initialized UDP socket for {self.ip_address}:{self.port}")
            except Exception as e:
                raise ConnectionError(f"Failed to create UDP socket: {e}")
        else:
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self.timeout)
                self._socket.connect((self.ip_address, self.port))
                logger.info(f"[eSSL/ZK] Connected TCP socket to {self.ip_address}:{self.port}")
            except socket.timeout:
                raise ConnectionError(f"Connection timeout to {self.ip_address}:{self.port} after {self.timeout}s")
            except socket.error as e:
                raise ConnectionError(f"Failed to connect to {self.ip_address}:{self.port}: {e}")

    def _send_command(self, command: int, data: bytes = b"") -> bytes:
        """Send ZK binary command packet and receive response."""
        if not self._socket:
            self._connect_socket()
        
        self._reply_id = (self._reply_id + 1) & 0xFFFF
        buf = struct.pack("<HHHH", command, 0, self._session_id, self._reply_id) + data
        chksum = _calc_zk_checksum(buf)
        sub_packet = struct.pack("<HHHH", command, chksum, self._session_id, self._reply_id) + data

        if self._is_udp:
            try:
                self._socket.sendto(sub_packet, (self.ip_address, self.port))
                response, _ = self._socket.recvfrom(1024)
                return response
            except socket.timeout:
                raise ConnectionError("Device did not respond in time (UDP)")
            except socket.error as e:
                raise ConnectionError(f"UDP Communication error: {e}")
        else:
            # TCP Framing: magic 0x5050 ('PP') (2B) + payload length (2B)
            packet = struct.pack("<HH", 0x5050, len(sub_packet)) + sub_packet
            try:
                self._socket.send(packet)
                response = self._socket.recv(1024)
                if not response:
                    raise ConnectionError("Empty response from device")
                return response
            except socket.timeout:
                raise ConnectionError("Device did not respond in time (TCP)")
            except socket.error as e:
                raise ConnectionError(f"TCP Communication error: {e}")
    
    def _decode_zk_time(self, t: int) -> Optional[datetime]:
        """Decode ZKTeco packed seconds timestamp into UTC datetime assuming org timezone (Asia/Kolkata)."""
        try:
            from app.core.org_time import ORG_TZ
            sec = t % 60
            t //= 60
            min_ = t % 60
            t //= 60
            hour = t % 24
            t //= 24
            day = (t % 31) + 1
            t //= 31
            month = (t % 12) + 1
            t //= 12
            year = t + 2000
            if 2000 <= year <= 2035 and 1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= min_ <= 59 and 0 <= sec <= 59:
                local_dt = datetime(year, month, day, hour, min_, sec, tzinfo=ORG_TZ)
                return local_dt.astimezone(timezone.utc)
        except Exception:
            pass
        return None

    def _parse_attendance_record(self, record_bytes: bytes) -> Optional[RawAttendanceRecord]:
        """Parse a single 40-byte attendance record from eSSL/ZKTeco binary format."""
        if len(record_bytes) < 40:
            return None
        try:
            from app.core.org_time import ORG_TZ

            # 1. Extract User ID
            user_id = record_bytes[14:24].rstrip(b'\x00').decode('ascii', errors='ignore').strip()
            if not user_id:
                user_id = record_bytes[0:10].rstrip(b'\x00').decode('ascii', errors='ignore').strip()
            if not user_id:
                user_id = record_bytes[2:10].rstrip(b'\x00').decode('ascii', errors='ignore').strip()
            if not user_id:
                return None
            
            # Clean non-printable characters from user_id
            user_id = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")).strip()
            if not user_id:
                return None

            punch_dt = None

            # 2a. Try ZK encoded seconds at offset 27..31 (standard for modern TFT firmware)
            if len(record_bytes) >= 31:
                t27 = struct.unpack('<I', record_bytes[27:31])[0]
                punch_dt = self._decode_zk_time(t27)

            # 2b. Try ZK bitfield timestamp at offset 0..4
            if not punch_dt:
                t0 = struct.unpack('<I', record_bytes[0:4])[0]
                sec = t0 & 0x3F
                min_ = (t0 >> 6) & 0x3F
                hour = (t0 >> 12) & 0x1F
                day = (t0 >> 17) & 0x1F
                month = (t0 >> 22) & 0x0F
                year = ((t0 >> 26) & 0x3F) + 2000
                if 2000 <= year <= 2035 and 1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= min_ <= 59 and 0 <= sec <= 59:
                    try:
                        local_dt = datetime(year, month, day, hour, min_, sec, tzinfo=ORG_TZ)
                        punch_dt = local_dt.astimezone(timezone.utc)
                    except ValueError:
                        pass

            # 2c. Try ZK bitfield at offset 4..8
            if not punch_dt:
                t4 = struct.unpack('<I', record_bytes[4:8])[0]
                sec = t4 & 0x3F
                min_ = (t4 >> 6) & 0x3F
                hour = (t4 >> 12) & 0x1F
                day = (t4 >> 17) & 0x1F
                month = (t4 >> 22) & 0x0F
                year = ((t4 >> 26) & 0x3F) + 2000
                if 2000 <= year <= 2035 and 1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= min_ <= 59 and 0 <= sec <= 59:
                    try:
                        local_dt = datetime(year, month, day, hour, min_, sec, tzinfo=ORG_TZ)
                        punch_dt = local_dt.astimezone(timezone.utc)
                    except ValueError:
                        pass

            # 2d. Fallback to byte positions 21..26
            if not punch_dt and len(record_bytes) >= 27:
                y = record_bytes[21] + 2000 if record_bytes[21] < 100 else record_bytes[21]
                m = record_bytes[22]
                d = record_bytes[23]
                h = record_bytes[24]
                mi = record_bytes[25]
                s = record_bytes[26]
                try:
                    local_dt = datetime(y, m, d, h, mi, s, tzinfo=ORG_TZ)
                    punch_dt = local_dt.astimezone(timezone.utc)
                except ValueError:
                    pass

            if not punch_dt:
                return None

            # Check punch_status at byte 31 first, fallback to byte 29
            b31 = record_bytes[31] if len(record_bytes) > 31 else 255
            punch_status = b31 if b31 in (0, 1, 4, 5) else (record_bytes[29] if len(record_bytes) > 29 else 0)

            # Check verify_type at byte 26 first, fallback to byte 28
            b26 = record_bytes[26] if len(record_bytes) > 26 else 255
            verify_type_code = b26 if b26 in (0, 1, 2, 3, 4, 6, 7, 15) else (record_bytes[28] if len(record_bytes) > 28 else 1)
            
            punch_type_map = {0: "IN", 1: "OUT", 4: "OUT", 5: "IN"}
            verify_type_map = {0: "FP", 1: "FP", 2: "CARD", 3: "PIN", 4: "FACE", 6: "FACE", 7: "PALM", 15: "PALM"}
            
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

    def _ensure_authenticated(self) -> None:
        """Ensure UDP or TCP socket is connected and session is authenticated."""
        if self._session_id != 0 and self._socket:
            return
            
        protocols_to_try = [True, False] if not self.use_tcp else [False]
        last_err = None
        
        for try_udp in protocols_to_try:
            self._is_udp = try_udp
            self._session_id = 0
            self._reply_id = 0
            self._connect_socket()
            
            try:
                response = self._send_command(CMD_CONNECT)
                if len(response) < 8:
                    raise ConnectionError("Invalid response from device (too short)")
                
                if self._is_udp:
                    reply_cmd = struct.unpack_from('<H', response, 0)[0]
                    self._session_id = struct.unpack_from('<H', response, 4)[0]
                else:
                    reply_cmd = struct.unpack_from('<H', response, 4)[0]
                    self._session_id = struct.unpack_from('<H', response, 8)[0]
                
                if reply_cmd != 2000 and reply_cmd != 2005:
                    raise ConnectionError(f"Device returned error code: {reply_cmd}")
                
                # Perform password auth if configured
                if self.password and self.password != "0":
                    try:
                        key = int(self.password)
                        h = 0
                        for i in range(32):
                            if (key & (1 << i)):
                                h = (h << 1) | 1
                            else:
                                h = h << 1
                        val = ((h & 0xFFFFFFFF) ^ self._session_id) & 0xFFFFFFFF
                        pwd_data = struct.pack('<I', val)
                        try:
                            self._send_command(1102, pwd_data)
                        except Exception as pwd_send_err:
                            logger.warning(f"[eSSL] Password command failed (bypassing): {pwd_send_err}")
                    except Exception as auth_err:
                        logger.warning(f"[eSSL] Password auth warning: {auth_err}")
                return
            except Exception as e:
                last_err = e
                if self._socket:
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                    self._socket = None
        
        raise ConnectionError(f"Failed to authenticate with biometric device: {last_err}")

    def __enter__(self):
        self._ensure_authenticated()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def test_connection(self) -> DeviceInfo:
        """Test connection and return device information."""
        start = time.time()
        self._ensure_authenticated()
        response_ms = (time.time() - start) * 1000
        proto_name = "UDP" if self._is_udp else "TCP"
        
        return DeviceInfo(
            model=f"eSSL/ZKTeco Device ({proto_name})",
            firmware_version="v8.0.1",
            device_time=datetime.now(timezone.utc),
            registered_users=0,
            last_attendance_time=None,
            response_time_ms=round(response_ms, 2),
        )
    
    def fetch_attendance(
        self,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        last_id: Optional[str] = None,
    ) -> list[RawAttendanceRecord]:
        """Fetch attendance records for the specified period."""
        records = []
        
        # Primary Strategy: Use pyzk for 100% complete and reliable data stream
        try:
            from zk import ZK
            from app.core.org_time import ORG_TZ

            pwd_int = 0
            try:
                pwd_int = int(self.password) if self.password and self.password != "0" else 0
            except ValueError:
                pwd_int = 0

            try:
                if pwd_int > 0:
                    zk = ZK(self.ip_address, port=self.port, timeout=self.timeout, password=pwd_int)
                    conn = zk.connect()
                else:
                    zk = ZK(self.ip_address, port=self.port, timeout=self.timeout)
                    conn = zk.connect()
            except Exception as conn_err:
                logger.warning(f"[eSSL/pyzk] Password connection failed ({conn_err}), retrying without password...")
                zk = ZK(self.ip_address, port=self.port, timeout=self.timeout)
                conn = zk.connect()
            try:
                raw_atts = conn.get_attendance()
                for att in raw_atts:
                    if not att.timestamp or not att.user_id:
                        continue
                    
                    user_id_str = str(att.user_id).strip()
                    
                    # Convert naive timestamp to ORG_TZ and then UTC
                    local_dt = att.timestamp.replace(tzinfo=ORG_TZ) if att.timestamp.tzinfo is None else att.timestamp.astimezone(ORG_TZ)
                    utc_dt = local_dt.astimezone(timezone.utc)

                    if from_dt and to_dt:
                        f_dt = from_dt if from_dt.tzinfo else from_dt.replace(tzinfo=timezone.utc)
                        t_dt = to_dt if to_dt.tzinfo else to_dt.replace(tzinfo=timezone.utc)
                        if not (f_dt <= utc_dt <= t_dt):
                            continue

                    punch_type_str = "OUT" if att.punch in (1, 4) else "IN"
                    verify_type_map = {0: "FP", 1: "FP", 2: "CARD", 3: "PIN", 4: "FACE", 6: "FACE", 7: "PALM", 15: "PALM"}
                    verify_str = verify_type_map.get(att.status, "FP")

                    records.append(
                        RawAttendanceRecord(
                            device_user_id=user_id_str,
                            punch_timestamp=utc_dt,
                            verification_type=verify_str,
                            punch_type=punch_type_str,
                            raw_data={
                                "user_id": user_id_str,
                                "timestamp": att.timestamp.isoformat(),
                                "status": att.status,
                                "punch": att.punch,
                            }
                        )
                    )
            finally:
                try:
                    conn.disconnect()
                except Exception:
                    pass
            logger.info(f"[eSSL/pyzk] Successfully fetched {len(records)} attendance records from {self.ip_address}")
            return records
        except Exception as pyzk_err:
            logger.warning(f"[eSSL/pyzk] pyzk fetch failed ({pyzk_err}), falling back to socket protocol")

        # Fallback Strategy: Binary socket protocol
        self._ensure_authenticated()
        try:
            # 1. Send CMD_GET_ATTLOG (13)
            self._reply_id = (self._reply_id + 1) & 0xFFFF
            buf = struct.pack("<HHHH", CMD_GET_ATTLOG, 0, self._session_id, self._reply_id)
            chksum = _calc_zk_checksum(buf)
            sub_packet = struct.pack("<HHHH", CMD_GET_ATTLOG, chksum, self._session_id, self._reply_id)
            
            if self._is_udp:
                self._socket.sendto(sub_packet, (self.ip_address, self.port))
            else:
                packet = struct.pack("<HH", 0x5050, len(sub_packet)) + sub_packet
                self._socket.send(packet)
                
            all_bytes = b""
            old_timeout = self._socket.gettimeout()
            self._socket.settimeout(1.5)
            
            # 2. Stream incoming data packets (cmd = 1501 or data chunks)
            for _ in range(500):
                try:
                    if self._is_udp:
                        resp, _ = self._socket.recvfrom(4096)
                        if len(resp) >= 12:
                            cmd = struct.unpack_from('<H', resp, 0)[0]
                            if cmd == 1501: # DATA chunk packet
                                all_bytes += resp[12:] # strip 8B header + 4B chunk seq
                            elif len(resp) > 8 and cmd not in (2000, 2005, 1500):
                                all_bytes += resp[8:]
                    else:
                        resp = self._socket.recv(4096)
                        if len(resp) > 16:
                            all_bytes += resp[16:]
                except (socket.timeout, socket.error):
                    break
                    
            self._socket.settimeout(old_timeout)
            
            # 3. Parse attendance records (40 bytes per record)
            record_size = 40
            for i in range(0, len(all_bytes) - record_size + 1, record_size):
                record_bytes = all_bytes[i:i + record_size]
                record = self._parse_attendance_record(record_bytes)
                if record:
                    if from_dt and to_dt:
                        f_dt = from_dt if from_dt.tzinfo else from_dt.replace(tzinfo=timezone.utc)
                        t_dt = to_dt if to_dt.tzinfo else to_dt.replace(tzinfo=timezone.utc)
                        p_dt = record.punch_timestamp if record.punch_timestamp.tzinfo else record.punch_timestamp.replace(tzinfo=timezone.utc)
                        if f_dt <= p_dt <= t_dt:
                            records.append(record)
                    else:
                        records.append(record)
                        
            logger.info(f"[eSSL] Successfully fetched {len(records)} attendance records from {self.ip_address}")
        except Exception as e:
            logger.error(f"[eSSL] Failed to fetch attendance: {e}")
            raise
        
        return records
    
    def get_registered_users(self) -> list[dict]:
        """Return list of registered users on the device."""
        self._ensure_authenticated()
        
        users = []
        try:
            response = self._send_command(CMD_GET_USERINFO)
            offset = 8 if self._is_udp else 16
            if len(response) > offset:
                data = response[offset:]
                user_size = 72
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
        """Close the UDP or TCP connection."""
        if self._socket:
            try:
                self._send_command(CMD_EXIT)
            except Exception:
                pass
            finally:
                self._socket.close()
                self._socket = None
                self._session_id = 0
                logger.info(f"[eSSL] Disconnected from {self.ip_address}")
