"""
Authentication Manager for ImxUp application.
Handles all authentication-related operations including credentials, sessions, and API keys.
"""

import os
import configparser
import hashlib
import base64
from typing import Optional, Tuple, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

from imxup_constants import (
    ENCRYPTION_ITERATIONS, ENCRYPTION_KEY_LENGTH,
    ERROR_NO_CREDENTIALS, CONFIG_DIR_NAME, CONFIG_FILE_NAME
)
from imxup_exceptions import (
    AuthenticationError, CredentialError, APIKeyError,
    EncryptionError, ConfigurationError
)


class AuthenticationManager:
    """Manages authentication for ImxUp application"""
    
    def __init__(self):
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.api_key: Optional[str] = None
        self.auth_type: str = "username_password"
        self.config_path = self._get_config_path()
        self._encryption_key: Optional[bytes] = None
        
    def _get_config_path(self) -> str:
        """Get the configuration file path"""
        base_dir = os.path.join(os.path.expanduser("~"), CONFIG_DIR_NAME)
        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, CONFIG_FILE_NAME)
    
    def _get_encryption_key(self) -> bytes:
        """Generate or retrieve the encryption key"""
        if self._encryption_key:
            return self._encryption_key
            
        try:
            # Derive key from system properties
            machine_id = os.environ.get('COMPUTERNAME', 'default')
            user_id = os.environ.get('USERNAME', 'user')
            salt_string = f"{machine_id}-{user_id}-imxup"
            salt = hashlib.sha256(salt_string.encode()).digest()
            
            kdf = PBKDF2(
                algorithm=hashes.SHA256(),
                length=ENCRYPTION_KEY_LENGTH,
                salt=salt,
                iterations=ENCRYPTION_ITERATIONS,
            )
            key = base64.urlsafe_b64encode(kdf.derive(b"imxup-password-key"))
            self._encryption_key = key
            return key
        except Exception as e:
            raise EncryptionError(f"Failed to generate encryption key: {e}")
    
    def encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        try:
            key = self._get_encryption_key()
            f = Fernet(key)
            return f.encrypt(data.encode()).decode()
        except Exception as e:
            raise EncryptionError(f"Failed to encrypt data: {e}")
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        try:
            key = self._get_encryption_key()
            f = Fernet(key)
            return f.decrypt(encrypted_data.encode()).decode()
        except Exception:
            # Return empty string if decryption fails (backward compatibility)
            return ""
    
    def load_credentials(self) -> bool:
        """Load credentials from configuration file"""
        try:
            if not os.path.exists(self.config_path):
                return False
                
            config = configparser.ConfigParser()
            config.read(self.config_path)
            
            if 'CREDENTIALS' not in config:
                return False
                
            cred_section = config['CREDENTIALS']
            self.auth_type = cred_section.get('auth_type', 'username_password')
            
            if self.auth_type == 'username_password':
                self.username = cred_section.get('username')
                encrypted_password = cred_section.get('password', '')
                
                if self.username and encrypted_password:
                    self.password = self.decrypt_data(encrypted_password)
                    return bool(self.password)
                    
            elif self.auth_type == 'api_key':
                encrypted_api_key = cred_section.get('api_key', '')
                
                if encrypted_api_key:
                    self.api_key = self.decrypt_data(encrypted_api_key)
                    return bool(self.api_key)
                    
            # Fallback to environment variable for API key
            env_api_key = os.getenv('IMX_API')
            if env_api_key:
                self.api_key = env_api_key
                self.auth_type = 'api_key'
                return True
                
            return False
            
        except Exception as e:
            raise ConfigurationError(f"Failed to load credentials: {e}")
    
    def save_credentials(self, username: str = None, password: str = None, 
                        api_key: str = None) -> bool:
        """Save credentials to configuration file"""
        try:
            config = configparser.ConfigParser()
            
            # Read existing config if it exists
            if os.path.exists(self.config_path):
                config.read(self.config_path)
            
            # Ensure CREDENTIALS section exists
            if 'CREDENTIALS' not in config:
                config['CREDENTIALS'] = {}
            
            # Save based on what's provided
            if api_key:
                config['CREDENTIALS']['auth_type'] = 'api_key'
                config['CREDENTIALS']['api_key'] = self.encrypt_data(api_key)
                self.api_key = api_key
                self.auth_type = 'api_key'
            elif username and password:
                config['CREDENTIALS']['auth_type'] = 'username_password'
                config['CREDENTIALS']['username'] = username
                config['CREDENTIALS']['password'] = self.encrypt_data(password)
                self.username = username
                self.password = password
                self.auth_type = 'username_password'
            else:
                return False
            
            # Write config to file
            with open(self.config_path, 'w') as f:
                config.write(f)
            
            return True
            
        except Exception as e:
            raise ConfigurationError(f"Failed to save credentials: {e}")
    
    def clear_credentials(self):
        """Clear stored credentials"""
        self.username = None
        self.password = None
        self.api_key = None
        self.auth_type = "username_password"
    
    def has_credentials(self) -> bool:
        """Check if valid credentials are available"""
        return bool((self.username and self.password) or self.api_key)
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests"""
        headers = {}
        
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        elif self.username and self.password:
            # Basic auth header
            import base64
            credentials = f"{self.username}:{self.password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers['Authorization'] = f"Basic {encoded}"
        
        return headers
    
    def get_auth_type(self) -> str:
        """Get the current authentication type"""
        return self.auth_type
    
    def validate_credentials(self) -> Tuple[bool, str]:
        """Validate that credentials are properly formatted"""
        if self.auth_type == 'api_key':
            if not self.api_key:
                return False, "API key is missing"
            if len(self.api_key) < 10:
                return False, "API key appears to be invalid"
            return True, "API key is valid"
            
        elif self.auth_type == 'username_password':
            if not self.username:
                return False, "Username is missing"
            if not self.password:
                return False, "Password is missing"
            if len(self.password) < 4:
                return False, "Password appears to be too short"
            return True, "Credentials are valid"
            
        return False, "Unknown authentication type"
    
    def get_credential_summary(self) -> str:
        """Get a summary of current credentials (for display)"""
        if self.api_key:
            # Show only first/last few characters of API key
            if len(self.api_key) > 8:
                masked = f"{self.api_key[:4]}...{self.api_key[-4:]}"
            else:
                masked = "****"
            return f"API Key: {masked}"
        elif self.username:
            return f"Username: {self.username}"
        else:
            return "No credentials configured"
    
    def rotate_encryption_key(self) -> bool:
        """Rotate the encryption key (re-encrypt all stored credentials)"""
        try:
            # Load current credentials
            if not self.load_credentials():
                return False
            
            # Clear encryption key cache
            self._encryption_key = None
            
            # Re-save with new encryption
            if self.api_key:
                return self.save_credentials(api_key=self.api_key)
            elif self.username and self.password:
                return self.save_credentials(
                    username=self.username, 
                    password=self.password
                )
            
            return False
            
        except Exception:
            return False