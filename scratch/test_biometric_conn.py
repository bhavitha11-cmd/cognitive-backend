import sys
import os
import socket
import struct
from datetime import datetime

sys.path.insert(0, os.path.abspath('.'))

def parse_all_device_logs():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)
    
    def calc_chksum(data):
        l = len(data)
        chk = 0
        i = 0
        while i < l:
            if i + 1 < l: val = struct.unpack('<H', data[i:i+2])[0]
            else: val = data[i]
            chk += val
            if chk > 0xFFFF: chk = (chk & 0xFFFF) + 1
            i += 2
        return (~chk) & 0xFFFF

    reply_id = 1
    session_id = 0
    buf = struct.pack('<HHHH', 1000, 0, session_id, reply_id)
    chk = calc_chksum(buf)
    sock.sendto(struct.pack('<HHHH', 1000, chk, session_id, reply_id), ('192.168.1.201', 4370))
    resp, _ = sock.recvfrom(1024)
    session_id = struct.unpack_from('<H', resp, 4)[0]

    # Auth
    key = 1234
    h = 0
    for i in range(32):
        if (key & (1 << i)): h = (h << 1) | 1
        else: h = h << 1
    val = ((h & 0xFFFFFFFF) ^ session_id) & 0xFFFFFFFF
    
    reply_id += 1
    buf = struct.pack('<HHHH', 1102, 0, session_id, reply_id) + struct.pack('<I', val)
    chk = calc_chksum(buf)
    sock.sendto(struct.pack('<HHHH', 1102, chk, session_id, reply_id) + struct.pack('<I', val), ('192.168.1.201', 4370))
    sock.recvfrom(1024)

    # Get Attlog
    reply_id += 1
    buf = struct.pack('<HHHH', 13, 0, session_id, reply_id)
    chk = calc_chksum(buf)
    sock.sendto(struct.pack('<HHHH', 13, chk, session_id, reply_id), ('192.168.1.201', 4370))
    
    all_b = b""
    sock.settimeout(1.5)
    for _ in range(500):
        try:
            p, _ = sock.recvfrom(4096)
            if len(p) > 8: all_b += p[8:]
        except Exception: break

    sock.close()

    parsed_records = []
    record_size = 40
    for i in range(0, len(all_b) - record_size + 1, record_size):
        r = all_b[i:i+40]
        if not any(r): continue
        
        # User ID is at bytes 14..24
        user_id = r[14:24].rstrip(b'\x00').decode('ascii', errors='ignore').strip()
        
        # Timestamp is packed at r[0:4] or r[26:30]
        t = struct.unpack('<I', r[0:4])[0]
        sec = t & 0x3F
        min_ = (t >> 6) & 0x3F
        hour = (t >> 12) & 0x1F
        day = (t >> 17) & 0x1F
        month = (t >> 22) & 0x0F
        year = ((t >> 26) & 0x3F) + 2000
        
        if 2000 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
            dt_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{min_:02d}:{sec:02d}"
            parsed_records.append((user_id, dt_str))

    print(f"Parsed {len(parsed_records)} valid attendance records from device!")
    print("Sample parsed records (first 10):")
    for u, dt in parsed_records[:10]:
        print(f"  User: {u:<10} | Punch Time: {dt}")

parse_all_device_logs()
