"""
Employee Mapping Service — manages mapping between ERP employees and device users.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models.biometric.bm_employee_mapping import BmEmployeeMapping
from app.models.biometric.bm_device import BmDevice

logger = logging.getLogger(__name__)


class EmployeeMappingService:
    def __init__(self, db: Session, current_user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.current_user_id = current_user_id
    
    def create_mapping(self, employee_id: uuid.UUID, device_id: uuid.UUID, biometric_user_id: str, method: str = 'MANUAL') -> BmEmployeeMapping:
        biometric_user_id = str(biometric_user_id).strip()
        # Check for any existing mapping (active OR inactive) for this employee+device
        existing_any = self.db.scalar(
            select(BmEmployeeMapping).where(
                BmEmployeeMapping.employee_id == employee_id,
                BmEmployeeMapping.device_id == device_id,
            )
        )
        if existing_any:
            if existing_any.is_active:
                raise ValueError(f"Active mapping already exists for employee {employee_id} and device {device_id}")
            # Reactivate the inactive mapping with new biometric_user_id
            existing_any.is_active = True
            existing_any.biometric_user_id = biometric_user_id
            existing_any.mapping_method = method
            existing_any.mapped_by = self.current_user_id
            self.db.commit()
            self.db.refresh(existing_any)
            self._reprocess_unmapped_logs(device_id)
            return existing_any

        mapping = BmEmployeeMapping(
            employee_id=employee_id,
            device_id=device_id,
            biometric_user_id=biometric_user_id,
            mapping_method=method,
            is_active=True,
            mapped_by=self.current_user_id,
        )
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        self._reprocess_unmapped_logs(device_id)
        return mapping
    
    def get_mapping(self, mapping_id: uuid.UUID) -> Optional[BmEmployeeMapping]:
        return self.db.scalar(
            select(BmEmployeeMapping).where(BmEmployeeMapping.id == mapping_id)
        )
    
    def get_mapping_by_employee_device(self, employee_id: uuid.UUID, device_id: uuid.UUID) -> Optional[BmEmployeeMapping]:
        return self.db.scalar(
            select(BmEmployeeMapping).where(
                BmEmployeeMapping.employee_id == employee_id,
                BmEmployeeMapping.device_id == device_id,
                BmEmployeeMapping.is_active == True,
            )
        )
    
    def get_mapping_by_device_user(self, device_id: uuid.UUID, biometric_user_id: str) -> Optional[BmEmployeeMapping]:
        return self.db.scalar(
            select(BmEmployeeMapping).where(
                BmEmployeeMapping.device_id == device_id,
                BmEmployeeMapping.biometric_user_id == biometric_user_id,
                BmEmployeeMapping.is_active == True,
            )
        )
    
    def list_mappings(
        self,
        device_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BmEmployeeMapping], int]:
        q = select(BmEmployeeMapping).where(BmEmployeeMapping.is_active == True)
        
        if device_id:
            q = q.where(BmEmployeeMapping.device_id == device_id)
        if employee_id:
            q = q.where(BmEmployeeMapping.employee_id == employee_id)
            
        from sqlalchemy import func
        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        
        q = q.order_by(BmEmployeeMapping.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        mappings = list(self.db.scalars(q).all())
        return mappings, total
    
    def update_mapping(self, mapping_id: uuid.UUID, data: dict) -> Optional[BmEmployeeMapping]:
        mapping = self.get_mapping(mapping_id)
        if not mapping:
            return None
            
        if "biometric_user_id" in data:
            mapping.biometric_user_id = str(data["biometric_user_id"]).strip()
        if "is_active" in data:
            mapping.is_active = data["is_active"]
            
        mapping.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(mapping)
        self._reprocess_unmapped_logs(mapping.device_id)
        return mapping
    
    def delete_mapping(self, mapping_id: uuid.UUID) -> bool:
        mapping = self.get_mapping(mapping_id)
        if not mapping:
            return False
        mapping.is_active = False
        mapping.updated_by = self.current_user_id
        self.db.commit()
        return True
    
    def _reprocess_unmapped_logs(self, device_id: uuid.UUID):
        """Re-evaluate existing unmapped raw logs for device to link to newly created mappings."""
        try:
            from app.models.biometric.bm_raw_log import BmRawLog
            from app.services.biometric.normalization_service import find_employee_mapping, NormalizationService

            unmapped_logs = list(self.db.scalars(
                select(BmRawLog).where(
                    BmRawLog.device_id == device_id,
                    BmRawLog.employee_mapping_id == None
                )
            ).all())

            if not unmapped_logs:
                return

            raw_ids = []
            for r in unmapped_logs:
                m = find_employee_mapping(self.db, device_id, r.device_user_id)
                if m:
                    r.employee_mapping_id = m.id
                    raw_ids.append(r.id)

            self.db.commit()

            if raw_ids:
                norm_svc = NormalizationService(self.db)
                norm_svc.batch_normalize(raw_ids)
        except Exception as e:
            logger.error(f"[EmployeeMappingService] Failed reprocessing unmapped logs: {e}")

    def bulk_import_mappings(self, items: list) -> dict:
        result = {"created": 0, "skipped": 0, "errors": 0, "error_details": []}
        from app.models.employee import Employee
        for item in items:
            try:
                emp_code = getattr(item, "employee_code", None) or item.get("employee_code")
                bio_id = getattr(item, "biometric_user_id", None) or item.get("biometric_user_id")
                device_serial = getattr(item, "device_serial", None) or item.get("device_serial")

                if not emp_code or not bio_id or not device_serial:
                    raise ValueError("Missing required fields: employee_code, biometric_user_id, device_serial")

                device = self.db.scalar(select(BmDevice).where(BmDevice.serial_number == device_serial))
                if not device:
                    raise ValueError(f"Device with serial '{device_serial}' not found")

                emp = self.db.scalar(select(Employee).where(Employee.employee_code == emp_code))
                if not emp:
                    raise ValueError(f"Employee with code '{emp_code}' not found")

                self.create_mapping(
                    employee_id=emp.id,
                    device_id=device.id,
                    biometric_user_id=str(bio_id).strip(),
                    method="BULK_IMPORT"
                )
                result["created"] += 1
            except Exception as e:
                result["errors"] += 1
                result["error_details"].append({"item": str(item), "error": str(e)})

        return result

    def auto_map_employees(self, device_id: uuid.UUID, match_by: str = 'employee_code') -> dict:
        result = {"created": 0, "skipped": 0, "unmatched": []}
        from app.models.employee import Employee
        from app.models.biometric.bm_raw_log import BmRawLog

        # Find all unique device_user_ids in raw logs for this device that have no active mapping
        raw_user_ids = list(self.db.scalars(
            select(BmRawLog.device_user_id)
            .where(BmRawLog.device_id == device_id)
            .distinct()
        ).all())

        employees = list(self.db.scalars(select(Employee).where(Employee.is_active == True)).all())
        emp_code_map = {e.employee_code.lower().strip(): e for e in employees if e.employee_code}

        for uid in raw_user_ids:
            if not uid:
                continue
            uid_str = str(uid).strip()
            import re
            digits = re.sub(r'\D', '', uid_str)

            matched_emp = None
            if match_by == 'employee_code':
                # Try exact code, lowercase, or EMP/CET-prefix formats
                candidates = [
                    uid_str.lower(),
                    f"cet-{uid_str}".lower(),
                    f"cet-{digits}".lower() if digits else "",
                    f"cet-{digits.zfill(3)}".lower() if digits else "",
                    f"emp-{uid_str}".lower(),
                    f"emp-{digits}".lower() if digits else "",
                    f"emp-{digits.zfill(3)}".lower() if digits else ""
                ]
                for cand in candidates:
                    if cand in emp_code_map:
                        matched_emp = emp_code_map[cand]
                        break

            if matched_emp:
                try:
                    self.create_mapping(
                        employee_id=matched_emp.id,
                        device_id=device_id,
                        biometric_user_id=uid_str,
                        method="AUTO"
                    )
                    result["created"] += 1
                except ValueError:
                    result["skipped"] += 1
            else:
                result["unmatched"].append({"device_user_id": uid_str})

        return result

