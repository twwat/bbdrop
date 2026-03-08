"""
Keyring-based credential storage and encryption.

Manages encrypted credential storage in the OS keyring using Fernet (AES-128-CBC
+ HMAC-SHA256) with a CSPRNG master key. Handles migration from legacy SHA-256-
derived keys and from INI file storage.

Note: This is distinct from src/utils/credential_helpers.py, which contains
low-level crypto primitives (generate_fernet_key, etc.).
"""

import os
import hashlib
import getpass
import base64
import threading

from cryptography.fernet import Fernet
from src.utils.credential_helpers import generate_fernet_key
from src.utils.logger import log


class CredentialDecryptionError(Exception):
    """Raised when credential decryption fails"""
    pass

def _get_legacy_encryption_key():
    """Generate encryption key from system info (LEGACY - used for migration only).

    WARNING: This uses hostname+username which is predictable and insecure.
    Only called during one-time migration to decrypt old credentials.
    """
    hostname = os.getenv('COMPUTERNAME') or os.getenv('HOSTNAME') or 'localhost'
    username = os.getenv('USERNAME') or os.getenv('USER') or 'user'
    system_info = f"{username}{hostname}"
    key = hashlib.sha256(system_info.encode()).digest()
    return base64.urlsafe_b64encode(key)

_cached_master_key = None
_master_key_lock = threading.Lock()

def get_encryption_key():
    """Get the CSPRNG master Fernet key from OS keyring.

    On first call after upgrade, triggers one-time migration that re-encrypts
    all existing credentials from the old SHA-256-derived key to the new
    CSPRNG key.
    """
    global _cached_master_key
    # Fast path — no lock needed for read of already-cached value
    if _cached_master_key is not None:
        return _cached_master_key

    with _master_key_lock:
        # Double-check after acquiring lock
        if _cached_master_key is not None:
            return _cached_master_key

        try:
            import keyring
            key = keyring.get_password("bbdrop", "_master_key")
            if key:
                _cached_master_key = key
                return key
        except Exception as e:
            raise CredentialDecryptionError(
                "OS keyring is not available. Credentials cannot be accessed. "
                f"Install a keyring backend (e.g., SecretStorage on Linux): {e}"
            ) from e

        # No master key yet — first run after upgrade (or fresh install)
        key = _migrate_encryption_keys()
        _cached_master_key = key
        return key

def encrypt_password(password):
    """Encrypt password using Fernet with the CSPRNG master key."""
    key = get_encryption_key()
    f = Fernet(key)
    return f.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    """Decrypt password with proper error handling.

    Raises CredentialDecryptionError on failure to prevent silent auth failures.
    """
    if not encrypted_password:
        raise CredentialDecryptionError("No encrypted password provided")

    try:
        key = get_encryption_key()
        f = Fernet(key)
        return f.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        log(f"Failed to decrypt password: {e}", level="error", category="auth")
        raise CredentialDecryptionError(
            "Credential decryption failed. Your credentials may be corrupted. "
            "Please reconfigure via Settings > Credentials."
        ) from e

def get_credential(key, host_id=None):
    """Get credential from OS keyring.

    Args:
        key: Credential key (username, password, api_key)
        host_id: Optional host identifier. If provided, looks up host-specific credential first.

    Returns:
        The credential value, or empty string if not found.
    """
    effective_key = f"{host_id}_{key}" if host_id else key

    try:
        import keyring
        value = keyring.get_password("bbdrop", effective_key)
        if value:
            return value
        # Fall back to global key for legacy IMX compat (not other hosts)
        if host_id and host_id == "imx":
            value = keyring.get_password("bbdrop", key)
            if value:
                return value
    except ImportError:
        log("keyring not available — credentials inaccessible", level="error", category="auth")
    except Exception as e:
        log(f"Keyring error: {e}", level="error", category="auth")

    return ""

def set_credential(key, value, host_id=None):
    """Store credential in OS keyring.

    Args:
        key: Credential key (username, password, api_key)
        value: Credential value to store
        host_id: Optional host identifier for host-specific storage.

    Raises:
        CredentialDecryptionError: If keyring is not available.
    """
    effective_key = f"{host_id}_{key}" if host_id else key

    try:
        import keyring
        keyring.set_password("bbdrop", effective_key, value)
        log(f"Credential '{effective_key}' stored in OS keyring", level="debug", category="auth")
    except ImportError:
        raise CredentialDecryptionError("OS keyring not available. Cannot store credentials.")
    except Exception as e:
        raise CredentialDecryptionError(f"Failed to store credential: {e}") from e

def remove_credential(key, host_id=None):
    """Remove credential from OS keyring.

    Args:
        key: Credential key (username, password, api_key)
        host_id: Optional host identifier for host-specific removal.
    """
    effective_key = f"{host_id}_{key}" if host_id else key

    try:
        import keyring
        keyring.delete_password("bbdrop", effective_key)
    except Exception:
        pass  # Key may not exist

def migrate_credentials_from_ini():
    """Migrate credentials from INI file to OS keyring, then remove from INI"""
    import configparser
    from src.utils.paths import get_config_path
    config = configparser.ConfigParser()
    config_file = get_config_path()

    if not os.path.exists(config_file):
        return

    config.read(config_file, encoding='utf-8')
    if 'CREDENTIALS' not in config:
        return

    # Migrate only actual credentials (not cookies_enabled which stays in INI as a preference)
    migrated = False
    cookies_val = config['CREDENTIALS'].get('cookies_enabled', '')

    for key in ['username', 'password', 'api_key']:
        value = config['CREDENTIALS'].get(key, '')
        if value:
            set_credential(key, value)
            migrated = True

    # Update INI file - remove credentials but keep cookies_enabled
    if migrated:
        config.remove_section('CREDENTIALS')
        if cookies_val:
            config['CREDENTIALS'] = {'cookies_enabled': cookies_val}
        with open(config_file, 'w') as f:
            config.write(f)
        log("Migrated credentials from INI to Registry", level="info", category="auth")

def _migrate_encryption_keys():
    """One-time migration: re-encrypt all credentials from SHA-256-derived key to CSPRNG key.

    Called automatically on first run after upgrade when no master key exists in keyring.
    Reads from both keyring and QSettings (one last time) to capture all credentials,
    then re-encrypts with the new key and removes the QSettings entries.

    Returns:
        str: The new CSPRNG master key (base64-encoded, Fernet-compatible)
    """
    new_key = generate_fernet_key()
    old_key = _get_legacy_encryption_key()

    old_fernet = Fernet(old_key)
    new_fernet = Fernet(new_key)

    # All known credential keys that may hold Fernet-encrypted values
    encrypted_keys = [
        'password', 'api_key',
        'imx_password', 'imx_api_key',
        'turbo_password', 'turbo_api_key',
    ]

    # File host credential keys
    file_host_ids = [
        'rapidgator', 'fileboom', 'keep2share', 'tezfiles', 'filedot',
        'filespace', 'katfile',
    ]
    for fh_id in file_host_ids:
        encrypted_keys.append(f'file_host_{fh_id}_credentials')

    # Plaintext keys (just need to ensure they're in keyring)
    plaintext_keys = ['username', 'imx_username', 'turbo_username']

    # Scan QSettings for any proxy_*_password keys we might have missed
    proxy_keys = []
    try:
        from PyQt6.QtCore import QSettings
        qs = QSettings("bbdrop", "bbdrop")
        qs.beginGroup("Credentials")
        for qs_key in qs.allKeys():
            if qs_key.startswith('proxy_') and qs_key.endswith('_password'):
                if qs_key not in encrypted_keys:
                    encrypted_keys.append(qs_key)
                    proxy_keys.append(qs_key)
        qs.endGroup()
    except Exception:
        pass

    def _read_from_both(credential_key):
        """Read a credential from keyring first, then QSettings as fallback."""
        try:
            import keyring
            value = keyring.get_password("bbdrop", credential_key)
            if value:
                return value
        except Exception:
            pass
        try:
            from PyQt6.QtCore import QSettings
            qs = QSettings("bbdrop", "bbdrop")
            qs.beginGroup("Credentials")
            value = qs.value(credential_key, "")
            qs.endGroup()
            return value
        except Exception:
            return ""

    migrated_count = 0
    skipped_count = 0

    # Migrate encrypted credentials: decrypt with old key, re-encrypt with new key
    for cred_key in encrypted_keys:
        old_value = _read_from_both(cred_key)
        if not old_value:
            continue

        try:
            plaintext = old_fernet.decrypt(old_value.encode()).decode()
            new_encrypted = new_fernet.encrypt(plaintext.encode()).decode()
            set_credential(cred_key, new_encrypted)
            migrated_count += 1
        except Exception:
            # Can't decrypt — might be corrupted or already plaintext. Copy as-is.
            try:
                set_credential(cred_key, old_value)
                skipped_count += 1
            except Exception as e:
                log(f"Failed to migrate credential '{cred_key}': {e}",
                    level="warning", category="auth")

    # Migrate plaintext credentials (just ensure they're in keyring)
    for cred_key in plaintext_keys:
        value = _read_from_both(cred_key)
        if value:
            try:
                set_credential(cred_key, value)
            except Exception:
                pass

    # Store the new master key in keyring
    try:
        import keyring
        keyring.set_password("bbdrop", "_master_key", new_key)
    except Exception as e:
        log(f"CRITICAL: Failed to store master key in keyring: {e}",
            level="critical", category="auth")
        raise CredentialDecryptionError(
            f"Cannot store master encryption key in OS keyring: {e}"
        ) from e

    # Clean up: remove QSettings Credentials group
    try:
        from PyQt6.QtCore import QSettings
        qs = QSettings("bbdrop", "bbdrop")
        qs.beginGroup("Credentials")
        for qs_key in qs.allKeys():
            qs.remove(qs_key)
        qs.endGroup()
        qs.sync()
    except Exception:
        pass  # QSettings cleanup is best-effort

    log(f"Encryption key migration complete: {migrated_count} re-encrypted, "
        f"{skipped_count} copied as-is", level="info", category="auth")

    return new_key


def setup_secure_password():
    """Interactive setup for secure password storage"""
    print("Setting up secure password storage for imx.to")
    print("This will store an encrypted version of your password in OS keyring")
    print("")

    username = input("Enter your imx.to username: ")
    password = getpass.getpass("Enter your imx.to password: ")

    # Save credentials without testing (since DDoS-Guard might block login)
    print("Saving credentials...")
    if _save_credentials(username, password):
        print("[OK] Credentials saved successfully!")
        print("Note: Login test was skipped due to potential DDoS-Guard protection.")
        print("You can test the credentials by running an upload.")
        return True
    else:
        log("Failed to save credentials.", level="error", category="auth")
        return False

def _save_credentials(username, password):
    """Save credentials to OS keyring"""
    set_credential('username', username)
    set_credential('password', encrypt_password(password))
    log("Username and encrypted password saved to Registry", level="info", category="auth")
    return True
