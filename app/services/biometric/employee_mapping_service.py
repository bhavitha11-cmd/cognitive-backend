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
            mapping.biometric_user_id = data["biometric_user_id"]
        if "is_active" in data:
            mapping.is_active = data["is_active"]
            
        mapping.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(mapping)
        return mapping
    
    def delete_mapping(self, mapping_id: uuid.UUID) -> bool:
        mapping = self.get_mapping(mapping_id)
        if not mapping:
            return False
        mapping.is_active = False
        mapping.updated_by = self.current_user_id
        self.db.commit()
        return True
    
    def bulk_import(self, items: list[dict], db: Session) -> dict:
        result = {"created": 0, "skipped": 0, "errors": 0, "error_details": []}
        
        for item in items:
            try:
                emp_code = item.get("employee_code")
                bio_id = item.get("biometric_user_id")
                device_serial = item.get("device_serial")
                
                if not emp_code or not bio_id or not device_serial:
                    raise ValueError("Missing required fields")
                
                # We assume a CoreEmployee model exists or we just rely on ID for now.
                # Usually we'd lookup Employee by code here. 
                # For simplicity, assuming caller passes actual UUIDs or we lookup via raw query
                # Here we just use basic error handling as placeholder
                raise NotImplementedError("Requires Employee model lookup")
                
            except Exception as e:
                result["errors"] += 1
                result["error_details"].append({"item": item, "error": str(e)})
                
        return result
        
    def auto_map(self, device_id: uuid.UUID, connector, match_by: str = 'employee_code') -> dict:
        result = {"created": 0, "unmatched": 0}
        try:
            # fetch users from device
            users = connector.fetch_users()
            for user in users:
                # lookup employee
                pass
        except Exception as e:
            logger.error(f"[EmployeeMapping] Auto-map error: {e}")
            
        return result
