#!/usr/bin/env python3
"""TDD tests for credential migration Step 2 safety.

Tests for the bug where decrypt_password() failure could mean either:
1. Value is plaintext (should encrypt)
2. Value is already encrypted but undecryptable (should NOT re-encrypt)

The fix uses _looks_encrypted() to distinguish structurally.
"""

import pytest
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet

from src.utils.credential_helpers import generate_fernet_key
from src.utils.credentials import (
    encrypt_password,
    decrypt_password,
    CredentialDecryptionError,
)


class TestLooksEncrypted:
    """Test the _looks_encrypted() helper (to be added)."""

    def test_fernet_token_looks_encrypted(self):
        """Fernet token (gAAAAA...) is recognized as encrypted."""
        from src.utils.credentials import _looks_encrypted

        # Create a real Fernet token
        key = generate_fernet_key()
        f = Fernet(key)
        token = f.encrypt(b"test").decode()

        # Should start with gAAAAA (0x80 version + timestamp)
        assert token.startswith('gAAAAA')
        assert _looks_encrypted(token) is True

    def test_plaintext_username_not_encrypted(self):
        """Plaintext username does not look encrypted."""
        from src.utils.credentials import _looks_encrypted

        assert _looks_encrypted("myusername") is False
        assert _looks_encrypted("user123") is False
        assert _looks_encrypted("test.user") is False

    def test_garbage_starting_with_g_not_encrypted(self):
        """Garbage starting with 'g' but not 'gAAAAA' is not encrypted."""
        from src.utils.credentials import _looks_encrypted

        assert _looks_encrypted("gabage_data") is False
        assert _looks_encrypted("gXXXX") is False

    def test_non_string_not_encrypted(self):
        """Non-string values return False."""
        from src.utils.credentials import _looks_encrypted

        assert _looks_encrypted(None) is False
        assert _looks_encrypted(123) is False
        assert _looks_encrypted("") is False


class TestMigrateImxCredentialsStep2Safety:
    """Test that Step 2 of migrate_imx_credentials is safe.

    Step 2 loop (lines 215-224):
      for key in ['imx_username', 'turbo_username']:
          value = get_credential(key)
          if not value:
              continue
          try:
              decrypt_password(value)
          except Exception:
              encrypted = encrypt_password(value)
              set_credential(key, encrypted)
              log(...)

    The bug: "decrypt failed" is assumed to mean "plaintext", but it could
    mean "already encrypted but undecryptable (corrupted or key mismatch)".

    The fix: Only encrypt if value doesn't look encrypted (doesn't start with 'gAAAAA').
    """

    @pytest.fixture
    def mock_keyring(self, monkeypatch):
        """Setup mock keyring with a working master key."""
        import src.utils.credentials as creds_module

        # Generate a fresh master key
        master_key = generate_fernet_key()

        # Cache it so encrypt/decrypt work
        creds_module._cached_master_key = master_key

        # Mock keyring to return this key
        keyring_data = {"bbdrop": {"_master_key": master_key}}

        def mock_get_password(service, key):
            return keyring_data.get(service, {}).get(key)

        def mock_set_password(service, key, value):
            if service not in keyring_data:
                keyring_data[service] = {}
            keyring_data[service][key] = value

        monkeypatch.setattr("keyring.get_password", mock_get_password)
        monkeypatch.setattr("keyring.set_password", mock_set_password)

        yield keyring_data

        # Cleanup cache
        creds_module._cached_master_key = None

    def test_plaintext_value_is_encrypted(self, mock_keyring):
        """Test (a): Plaintext value is encrypted and stored."""
        from src.utils.credentials import migrate_imx_credentials, get_credential

        # Setup: plaintext username in keyring
        mock_keyring["bbdrop"]["imx_username"] = "myusername"

        # Run migration
        migrate_imx_credentials()

        # Check: stored value looks encrypted
        stored = get_credential("imx_username")
        assert stored.startswith("gAAAAA"), "Value should be encrypted with Fernet"

        # Check: decrypts back to original
        decrypted = decrypt_password(stored)
        assert decrypted == "myusername"

    def test_already_encrypted_value_not_re_encrypted(self, mock_keyring):
        """Test (b): Already-encrypted value is NOT re-encrypted (double-wrap bug)."""
        from src.utils.credentials import migrate_imx_credentials, get_credential

        # Setup: encrypt a value with current key
        original_plaintext = "secret_password"
        encrypted_once = encrypt_password(original_plaintext)
        mock_keyring["bbdrop"]["imx_username"] = encrypted_once

        # Run migration
        migrate_imx_credentials()

        # Check: stored value is UNCHANGED (not re-encrypted)
        stored = get_credential("imx_username")
        assert stored == encrypted_once, "Already-encrypted value should not be modified"

        # Check: decrypts to original exactly once (no double-wrapping)
        decrypted = decrypt_password(stored)
        assert decrypted == original_plaintext

    def test_corrupted_encrypted_value_not_re_encrypted(self, mock_keyring, monkeypatch):
        """Test (c): Corrupted (undecryptable) encrypted value is left alone + error logged."""
        from src.utils.credentials import migrate_imx_credentials, get_credential

        # Setup: a value that LOOKS encrypted ('gAAAAA' + garbage) but fails to decrypt
        corrupted_token = "gAAAAA_corrupted_garbage_that_looks_like_fernet"
        mock_keyring["bbdrop"]["imx_username"] = corrupted_token

        # Mock log to capture error message
        logged_messages = []
        def mock_log(msg, level=None, category=None):
            logged_messages.append({"msg": msg, "level": level, "category": category})
        monkeypatch.setattr("src.utils.credentials.log", mock_log)

        # Run migration (should not raise)
        migrate_imx_credentials()

        # Check: stored value is UNCHANGED
        stored = get_credential("imx_username")
        assert stored == corrupted_token, "Corrupted encrypted value should not be modified"

        # Check: error was logged about the credential
        error_logs = [m for m in logged_messages if m.get("level") == "error"]
        assert len(error_logs) > 0, "Should have logged an error"
        # Find the migration-specific error log (not the decrypt_password error)
        migration_error = [m for m in error_logs if "encrypted but cannot be decrypted" in m["msg"]]
        assert len(migration_error) > 0, "Should log migration error about undecryptable encrypted value"
        assert "imx_username" in migration_error[0]["msg"]

    def test_turbo_username_also_protected(self, mock_keyring, monkeypatch):
        """Test that turbo_username is also protected (same Step 2 logic)."""
        from src.utils.credentials import migrate_imx_credentials, get_credential

        # Setup: plaintext turbo_username
        mock_keyring["bbdrop"]["turbo_username"] = "turbo_user"

        # Run migration
        migrate_imx_credentials()

        # Check: encrypted
        stored = get_credential("turbo_username")
        assert stored.startswith("gAAAAA")
        assert decrypt_password(stored) == "turbo_user"

    def test_empty_value_skipped(self, mock_keyring, monkeypatch):
        """Test that empty values are skipped (shouldn't try to encrypt)."""
        from src.utils.credentials import get_credential

        # No credentials set initially

        # Track set_credential calls
        set_calls = []
        def mock_set(key, value, host_id=None):
            set_calls.append((key, value, host_id))

        import src.utils.credentials as creds_module
        original_set = creds_module.set_credential
        monkeypatch.setattr("src.utils.credentials.set_credential", mock_set)

        # Run migration
        from src.utils.credentials import migrate_imx_credentials
        migrate_imx_credentials()

        # Check: no set_credential calls for imx_username or turbo_username
        username_calls = [c for c in set_calls if c[0] in ["imx_username", "turbo_username"]]
        assert len(username_calls) == 0, "Empty values should not trigger set_credential"

    def test_real_fernet_token_recognized_as_encrypted(self, mock_keyring, monkeypatch):
        """Test that a real Fernet token from a different key is recognized as encrypted."""
        from src.utils.credentials import migrate_imx_credentials, get_credential

        # Create a Fernet token with a DIFFERENT key (simulating key mismatch)
        different_key = generate_fernet_key()
        f = Fernet(different_key)
        token_different_key = f.encrypt(b"secret").decode()

        # Store this token (which will fail to decrypt with current key)
        mock_keyring["bbdrop"]["imx_username"] = token_different_key

        # Track set_credential calls
        set_calls = []
        def mock_set(key, value, host_id=None):
            set_calls.append((key, value, host_id))

        monkeypatch.setattr("src.utils.credentials.set_credential", mock_set)

        # Track error logs
        logged_messages = []
        def mock_log(msg, level=None, category=None):
            logged_messages.append({"msg": msg, "level": level, "category": category})
        monkeypatch.setattr("src.utils.credentials.log", mock_log)

        # Run migration
        migrate_imx_credentials()

        # Check: NOT re-encrypted (set_credential not called for imx_username)
        username_calls = [c for c in set_calls if c[0] == "imx_username"]
        # Either no calls (best case) or the call only happens to store the original
        if username_calls:
            assert username_calls[0][1] == token_different_key, \
                "Should keep original token, not re-encrypt it"

        # Check: error was logged about key mismatch
        error_logs = [m for m in logged_messages if m.get("level") == "error"]
        assert len(error_logs) > 0, "Should log error about undecryptable encrypted value"
