"""
Connection Profile Service — manages biometric device connection profiles.
"""
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.biometric.bm_connection_profile import BmConnectionProfile
from app.core.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)


class ConnectionProfileService:
    def __init__(self, db: Session, current_user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.current_user_id = current_user_id
    
    def create_profile(self, device_id: uuid.UUID, connection_type: str, config_dict: dict) -> BmConnectionProfile:
        existing_profile = self.get_profile_for_device(device_id)
        if existing_profile and 'password' in config_dict and (config_dict['password'] == '****' or not config_dict['password']):
            existing_config = self.get_decrypted_config(existing_profile.id)
            if 'password' in existing_config:
                config_dict['password'] = existing_config['password']

        config_json = json.dumps(config_dict)
        encrypted_config = encrypt_value(config_json)
        
        # Deactivate existing active profiles
        active_profiles = self.list_profiles(device_id)
        for p in active_profiles:
            if p.is_active:
                p.is_active = False
                p.updated_by = self.current_user_id
        
        profile = BmConnectionProfile(
            device_id=device_id,
            connection_type=connection_type,
            config_encrypted=encrypted_config,
            is_active=True,
            created_by=self.current_user_id,
            updated_by=self.current_user_id,
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile
    
    def get_profile(self, profile_id: uuid.UUID) -> Optional[BmConnectionProfile]:
        return self.db.scalar(
            select(BmConnectionProfile).where(BmConnectionProfile.id == profile_id)
        )
    
    def get_profile_for_device(self, device_id: uuid.UUID) -> Optional[BmConnectionProfile]:
        return self.db.scalar(
            select(BmConnectionProfile).where(
                BmConnectionProfile.device_id == device_id,
                BmConnectionProfile.is_active == True,
            )
        )
    
    def list_profiles(self, device_id: uuid.UUID) -> list[BmConnectionProfile]:
        return list(self.db.scalars(
            select(BmConnectionProfile).where(
                BmConnectionProfile.device_id == device_id
            ).order_by(BmConnectionProfile.created_at.desc())
        ).all())
    
    def update_profile(self, profile_id: uuid.UUID, data: dict) -> Optional[BmConnectionProfile]:
        profile = self.get_profile(profile_id)
        if not profile:
            return None
        
        if "is_active" in data and data["is_active"] is not None:
            if data["is_active"]:
                # Deactivate others
                active_profiles = self.list_profiles(profile.device_id)
                for p in active_profiles:
                    if p.id != profile.id and p.is_active:
                        p.is_active = False
            profile.is_active = data["is_active"]
        
        if "config_dict" in data and data["config_dict"]:
            new_config = data["config_dict"]
            if 'password' in new_config and (new_config['password'] == '****' or not new_config['password']):
                existing_config = self.get_decrypted_config(profile_id)
                if 'password' in existing_config and existing_config['password']:
                    new_config['password'] = existing_config['password']
            config_json = json.dumps(new_config)
            profile.config_encrypted = encrypt_value(config_json)
            
        profile.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(profile)
        return profile
    
    def delete_profile(self, profile_id: uuid.UUID) -> bool:
        profile = self.get_profile(profile_id)
        if not profile:
            return False
        self.db.delete(profile)
        self.db.commit()
        return True
    
    def get_decrypted_config(self, profile_id: uuid.UUID) -> dict:
        profile = self.get_profile(profile_id)
        if not profile or not profile.config_encrypted:
            return {}
        try:
            decrypted_str = decrypt_value(profile.config_encrypted)
            return json.loads(decrypted_str)
        except Exception as e:
            logger.error(f"[ConnectionProfile] Decryption error for profile {profile_id}: {e}")
            return {}
    
    def get_masked_config(self, profile_id: uuid.UUID) -> dict:
        config = self.get_decrypted_config(profile_id)
        masked_config = {}
        for k, v in config.items():
            if 'password' in k.lower() or 'secret' in k.lower():
                masked_config[k] = '****'
            else:
                masked_config[k] = v
        return masked_config
