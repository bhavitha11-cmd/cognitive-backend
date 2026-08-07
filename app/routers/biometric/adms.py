"""
ADMS (Automatic Device Management System) Push Router

Handles HTTP PUSH requests from ZKTeco/eSSL biometric devices operating in ADMS / Cloud Server mode.

Supported endpoints (supports both ADMS standard path and biometric sub-path):
- GET /iclock/cdata (Heartshake / Initial Registration)
- POST /iclock/cdata (Real-time Attendance Push)
- GET /iclock/getrequest (Server Command Polling)
- POST /iclock/devicecmd (Command Response)
"""

import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.session import get_db
from app.models.biometric.bm_device import BmDevice
from app.models.biometric.bm_raw_log import BmRawLog
from app.models.biometric.bm_employee_mapping import BmEmployeeMapping
from app.services.biometric.normalization_service import NormalizationService, find_employee_mapping
from app.core.org_time import ORG_TZ

logger = logging.getLogger(__name__)


router = APIRouter(tags=["ADMS Biometric Push"])


def _parse_adms_datetime(dt_str: str) -> Optional[datetime]:
    """Parse ADMS timestamp string 'YYYY-MM-DD HH:MM:SS' into UTC datetime."""
    try:
        dt_str = dt_str.strip()
        naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        local_dt = naive_dt.replace(tzinfo=ORG_TZ)
        return local_dt.astimezone(timezone.utc)
    except Exception as e:
        logger.warning(f"[ADMS] Failed to parse timestamp '{dt_str}': {e}")
        return None


@router.get("/iclock/cdata")
@router.get("/iclock/cdata.aspx")
@router.get("/adms/iclock/cdata")
@router.get("/adms/iclock/cdata.aspx")
def adms_handshake(
    SN: Optional[str] = Query(None),
    options: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """ADMS Initial Connection / Heartshake GET handler."""
    logger.info(f"[ADMS Push] Device Handshake: SN={SN}, options={options}")
    if SN:
        device = db.scalar(select(BmDevice).where(BmDevice.serial_number == SN))
        if device:
            device.last_seen_at = datetime.now(timezone.utc)
            device.status = "ACTIVE"
            db.commit()
    # ZKTeco ADMS specification requires returning OK
    return Response(content="OK", media_type="text/plain")


@router.post("/iclock/cdata")
@router.post("/iclock/cdata.aspx")
@router.post("/adms/iclock/cdata")
@router.post("/adms/iclock/cdata.aspx")
async def adms_push_attendance(
    request: Request,
    SN: Optional[str] = Query(None),
    table: Optional[str] = Query("ATTLOG"),
    db: Session = Depends(get_db),
):

    """
    ADMS Real-Time Attendance Push POST handler.
    Device sends tab-separated text payload of attendance logs:
    Format per line: <USER_ID>\\t<TIMESTAMP>\\t<PUNCH_STATE>\\t<VERIFY_TYPE>
    Example: CET010\\t2026-08-03 17:20:00\\t1\\t1
    """
    try:
        body_bytes = await request.body()
        raw_text = body_bytes.decode("utf-8", errors="ignore").strip()
        logger.info(f"[ADMS Push] Received payload for SN={SN}, table={table}, length={len(raw_text)}")

        if not raw_text:
            return Response(content="OK", media_type="text/plain")

        # Find device by Serial Number if provided, else fallback to first active device
        device = None
        if SN:
            device = db.scalar(select(BmDevice).where(BmDevice.serial_number == SN))
        if not device:
            device = db.scalar(select(BmDevice).where(BmDevice.is_active == True))

        device_id = device.id if device else None

        lines = raw_text.split("\n")
        saved_count = 0
        raw_log_ids = []

        punch_type_map = {"0": "IN", "1": "OUT", "4": "OUT", "5": "IN"}
        verify_map = {"0": "FP", "1": "FP", "2": "CARD", "3": "PIN", "4": "FACE", "6": "FACE", "7": "PALM", "15": "PALM"}

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            parts = line_str.split("\t")
            if len(parts) >= 2:
                user_id = parts[0].strip()
                timestamp_str = parts[1].strip()
                punch_state = parts[2].strip() if len(parts) > 2 else "0"
                verify_code = parts[3].strip() if len(parts) > 3 else "1"

                punch_dt = _parse_adms_datetime(timestamp_str)
                if not user_id or not punch_dt:
                    continue

                # Check duplicate raw log
                existing = None
                if device_id:
                    existing = db.scalar(
                        select(BmRawLog).where(
                            BmRawLog.device_id == device_id,
                            BmRawLog.device_user_id == user_id,
                            BmRawLog.punch_timestamp == punch_dt,
                        )
                    )

                if existing:
                    continue

                # Find employee mapping
                mapping_id = None
                if device_id:
                    mapping = find_employee_mapping(db, device_id, user_id)
                    if mapping:
                        mapping_id = mapping.id


                raw_log = BmRawLog(
                    device_id=device_id,
                    employee_mapping_id=mapping_id,
                    device_user_id=user_id,
                    punch_timestamp=punch_dt,
                    verification_type=verify_map.get(verify_code, "UNKNOWN"),
                    punch_type=punch_type_map.get(punch_state, "UNKNOWN"),
                    raw_payload={
                        "user_id": user_id,
                        "raw_line": line_str,
                        "adms_sn": SN,
                        "punch_state": punch_state,
                        "verify_code": verify_code,
                    },
                )
                db.add(raw_log)
                db.flush()
                saved_count += 1
                raw_log_ids.append(raw_log.id)

        db.commit()

        # Instantly normalize saved logs
        if raw_log_ids:
            norm_svc = NormalizationService(db)
            norm_svc.batch_normalize(raw_log_ids)

        if device:
            device.last_seen_at = datetime.now(timezone.utc)
            device.last_sync_at = datetime.now(timezone.utc)
            db.commit()

        logger.info(f"[ADMS Push] Successfully processed {saved_count} punches from SN={SN}")
        return Response(content=f"OK: {saved_count}", media_type="text/plain")

    except Exception as e:
        logger.error(f"[ADMS Push] Error processing push payload: {e}", exc_info=True)
        return Response(content="OK", media_type="text/plain")


@router.get("/iclock/getrequest")
@router.get("/iclock/getrequest.aspx")
@router.get("/adms/iclock/getrequest")
@router.get("/adms/iclock/getrequest.aspx")
def adms_get_request(SN: Optional[str] = Query(None)):
    """Device polls server for pending commands."""
    return Response(content="OK", media_type="text/plain")


@router.post("/iclock/devicecmd")
@router.post("/iclock/devicecmd.aspx")
@router.post("/adms/iclock/devicecmd")
@router.post("/adms/iclock/devicecmd.aspx")
def adms_device_cmd_response(SN: Optional[str] = Query(None)):
    """Device confirms execution of server command."""
    return Response(content="OK", media_type="text/plain")

