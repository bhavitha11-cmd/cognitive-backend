import uuid
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user
from app.schemas.biometric.health import ConnectionTestResult
from app.services.biometric.connection_profile_service import ConnectionProfileService
from app.services.biometric.device_service import DeviceService
from app.services.biometric.device_health_service import DeviceHealthService
from app.services.biometric.connectors.factory import ConnectorFactory

router = APIRouter(prefix="/test", tags=["Biometric Connection Test"])

@router.post("/{device_id}", response_model=ConnectionTestResult)
def test_connection(
    device_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Test connection to a biometric device.
    Returns device info on success, structured error on failure.
    """
    device_svc = DeviceService(db)
    profile_svc = ConnectionProfileService(db)
    health_svc = DeviceHealthService(db)
    
    device = device_svc.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    profile = profile_svc.get_profile_for_device(device_id)
    if not profile:
        raise HTTPException(status_code=422, detail="No active connection profile found for this device")
    
    start_ms = time.time() * 1000
    
    try:
        connector = ConnectorFactory.get_connector(
            device.vendor,
            profile.connection_type,
            profile.config_encrypted,
        )
        with connector:
            device_info = connector.test_connection()
        
        response_ms = time.time() * 1000 - start_ms
        
        # Update device health with successful test
        health_svc.update_health_from_test(device_id, {
            "connection_status": "ONLINE",
            "firmware_version": device_info.firmware_version,
            "registered_users_count": device_info.registered_users,
            "response_time_ms": int(response_ms),
        })
        
        # Update device last_seen_at
        device.last_seen_at = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
        db.commit()
        
        return ConnectionTestResult(
            status="connected",
            device_model=device_info.model,
            firmware_version=device_info.firmware_version,
            device_time=device_info.device_time,
            registered_users=device_info.registered_users,
            last_attendance_time=device_info.last_attendance_time,
            response_time_ms=round(response_ms, 2),
            message=f"Successfully connected to {device.device_name}",
        )
        
    except ConnectionError as e:
        err_str = str(e)
        health_svc.update_health_from_test(device_id, {
            "connection_status": "OFFLINE",
            "last_error": err_str,
        })
        db.commit()
        
        suggestions = _get_error_suggestions(err_str)
        return ConnectionTestResult(
            status="failed",
            error_code="CONNECTION_ERROR",
            message=err_str,
            suggestions=suggestions,
        )
    except Exception as e:
        err_str = str(e)
        health_svc.update_health_from_test(device_id, {
            "connection_status": "OFFLINE",
            "last_error": err_str,
        })
        db.commit()
        
        return ConnectionTestResult(
            status="failed",
            error_code="UNKNOWN_ERROR",
            message=f"Unexpected error: {err_str}",
            suggestions=["Check device configuration", "Contact support if issue persists"],
        )

def _get_error_suggestions(error: str) -> list[str]:
    suggestions = []
    err_lower = error.lower()
    if "timeout" in err_lower:
        suggestions = [
            "Check that the device IP address is correct",
            "Verify the device is powered on and connected to the network",
            "Check firewall rules allow TCP on the configured port",
            "Try increasing the timeout value in connection settings",
        ]
    elif "refused" in err_lower or "connect" in err_lower:
        suggestions = [
            "Verify the IP address and port are correct",
            "Ensure no other application is blocking the port",
            "Check device network configuration",
        ]
    elif "password" in err_lower or "auth" in err_lower:
        suggestions = [
            "Verify the device communication password",
            "Check device settings for the correct password",
        ]
    else:
        suggestions = [
            "Check device configuration settings",
            "Verify network connectivity",
            "Restart the device and try again",
        ]
    return suggestions
