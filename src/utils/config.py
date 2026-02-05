import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import platform

class ConfigManager:
    _instance = None
    _key = None
    _cipher_suite = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialize_key()
        return cls._instance

    def _initialize_key(self):
        # Use a consistent salt and machine-specific key generation
        # NOTE: In a real production app, use Windows DPAPI or OS KeyStore.
        # Here we simulate consistency using machine info.
        salt = b'manatoki_crawler_salt'
        machine_id = str(platform.node()) + str(platform.machine())
        password = machine_id.encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        self._key = base64.urlsafe_b64encode(kdf.derive(password))
        self._cipher_suite = Fernet(self._key)

    def encrypt_value(self, plain_text: str) -> str:
        if not plain_text:
            return ""
        try:
            encrypted_bytes = self._cipher_suite.encrypt(plain_text.encode())
            return encrypted_bytes.decode('utf-8')
        except Exception:
             # In case of error (e.g. empty string), return as is or handle it
            return plain_text

    def decrypt_value(self, encrypted_text: str) -> str:
        if not encrypted_text:
            return ""
        try:
            # Check if it looks encrypted (Fernet tokens are long)
            # If not, return as is (for migration)
            if len(encrypted_text) < 10: 
                 return encrypted_text
            
            decrypted_bytes = self._cipher_suite.decrypt(encrypted_text.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except Exception:
            # If decryption fails, assume it's plain text (lazy migration)
            return encrypted_text

# Singleton Instance
config_manager = ConfigManager()
