import base64
import hashlib
import logging
from cryptography.fernet import Fernet
from app.core.config import settings

logger = logging.getLogger(__name__)

_fernet_instance = None

def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        # Derive a 32-byte key from the SECRET_KEY using SHA-256
        key = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key_b64 = base64.urlsafe_b64encode(key)
        _fernet_instance = Fernet(key_b64)
    return _fernet_instance

def encrypt_value(value: str | None) -> str | None:
    """Encrypt a string value using the derived secret key."""
    if not value:
        return None
    try:
        f = _get_fernet()
        return f.encrypt(value.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to encrypt value: {e}")
        raise ValueError("Encryption failed") from e

def decrypt_value(encrypted_value: str | None) -> str | None:
    """Decrypt a string value. Returns the plain text if decryption succeeds or the input if it fails."""
    if not encrypted_value:
        return None
    try:
        f = _get_fernet()
        return f.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except Exception as e:
        # Log decryption error but avoid crashing the app
        logger.warning(f"Failed to decrypt value (value might be plain text or key changed): {e}")
        return encrypted_value
