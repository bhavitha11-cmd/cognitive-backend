"""
Connector Factory

Creates the appropriate connector for a given vendor + connection type.
To add a new vendor: only modify this file's _registry dict.
"""
import json
import logging
from app.services.biometric.connectors.base import BiometricConnector
from app.core.encryption import decrypt_value

logger = logging.getLogger(__name__)

class ConnectorFactory:
    _registry = {
        ("ESSL", "DIRECT"): "app.services.biometric.connectors.essl.essl_direct.ESSLDirectConnector",
        ("ESSL", "DATABASE"): "app.services.biometric.connectors.essl.essl_database.ESSLDatabaseConnector",
        ("ESSL", "REST_API"): "app.services.biometric.connectors.essl.essl_rest.ESSLRestConnector",
        ("ESSL", "ADMS_PUSH"): "app.services.biometric.connectors.essl.essl_adms.ESSLAdmsConnector",
        # Future vendors:
        # ("ZKTECO", "DIRECT"): "...zkteco...",
        # ("SUPREMA", "REST_API"): "...suprema...",
    }
    
    @classmethod
    def get_connector(cls, vendor: str, connection_type: str, encrypted_config: str) -> BiometricConnector:
        """
        Decrypt config and instantiate the correct connector.
        
        Args:
            vendor: Vendor identifier (ESSL, ZKTECO, etc.)
            connection_type: Connection method (DIRECT, DATABASE, etc.)
            encrypted_config: Fernet-encrypted JSON config string
        
        Returns:
            BiometricConnector instance ready to use
        """
        key = (vendor.upper(), connection_type.upper())
        class_path = cls._registry.get(key)
        if not class_path:
            raise ValueError(f"No connector registered for vendor='{vendor}' type='{connection_type}'")
        
        # Dynamically import connector class
        module_path, class_name = class_path.rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        connector_class = getattr(module, class_name)
        
        # Decrypt and parse config
        decrypted = decrypt_value(encrypted_config)
        config = json.loads(decrypted) if decrypted else {}
        
        logger.info(f"[ConnectorFactory] Creating {class_name} for {vendor}/{connection_type}")
        return connector_class(config)
    
    @classmethod
    def list_supported_vendors(cls) -> list[dict]:
        """Return list of supported vendor/connection_type combinations."""
        return [
            {"vendor": k[0], "connection_type": k[1]}
            for k in cls._registry.keys()
        ]
