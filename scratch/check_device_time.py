import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.services.biometric.connectors.essl.essl_direct import ESSLDirectConnector

connector = ESSLDirectConnector({"ip_address": "192.168.1.201", "port": 4370, "password": "1234"})
info = connector.test_connection()
print(f"Device Model: {info.model}")
print(f"Device Time: {info.device_time}")
print(f"Response Time: {info.response_time_ms} ms")
