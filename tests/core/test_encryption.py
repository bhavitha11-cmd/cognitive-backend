import pytest
from app.core.encryption import encrypt_value, decrypt_value

def test_encryption_decryption():
    test_val = "MySecret123!"
    encrypted = encrypt_value(test_val)
    assert encrypted is not None
    assert encrypted != test_val
    
    decrypted = decrypt_value(encrypted)
    assert decrypted == test_val

def test_encryption_none():
    assert encrypt_value(None) is None
    assert decrypt_value(None) is None
    assert encrypt_value("") is None
    assert decrypt_value("") is None

def test_decryption_failure():
    # If decryption fails (e.g. not base64/fernet formatted), it should return the original string
    bad_val = "not_encrypted_value"
    decrypted = decrypt_value(bad_val)
    assert decrypted == bad_val
