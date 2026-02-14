#!/usr/bin/env python3
"""Tests for CSPRNG credential key migration and generation."""

import base64
import pytest
from unittest.mock import patch, MagicMock, call
from cryptography.fernet import Fernet

from src.utils.credential_helpers import generate_fernet_key


class TestGenerateFernetKey:
    """Test CSPRNG Fernet key generation."""

    def test_generates_valid_fernet_key(self):
        """Key can construct a Fernet instance and round-trip encrypt/decrypt."""
        key = generate_fernet_key()
        f = Fernet(key)
        plaintext = b"test credential"
        encrypted = f.encrypt(plaintext)
        assert f.decrypt(encrypted) == plaintext

    def test_generates_unique_keys(self):
        """Each call produces a different key (CSPRNG, not deterministic)."""
        keys = {generate_fernet_key() for _ in range(10)}
        assert len(keys) == 10

    def test_key_is_correct_length(self):
        """Fernet requires a 32-byte key, base64url-encoded = 44 chars."""
        key = generate_fernet_key()
        assert len(key) == 44
        raw = base64.urlsafe_b64decode(key)
        assert len(raw) == 32

    def test_key_differs_from_legacy(self):
        """CSPRNG key is not the same as the old SHA-256(hostname+username) key."""
        from bbdrop import _get_legacy_encryption_key
        legacy_key = _get_legacy_encryption_key()
        csprng_key = generate_fernet_key()
        assert csprng_key != legacy_key.decode('ascii')


class TestGetEncryptionKey:
    """Test the new get_encryption_key() with keyring-based master key."""

    def test_returns_cached_key_on_second_call(self):
        """Second call returns cached key without hitting keyring."""
        import bbdrop
        original_cached = bbdrop._cached_master_key
        try:
            bbdrop._cached_master_key = "cached_test_key"
            result = bbdrop.get_encryption_key()
            assert result == "cached_test_key"
        finally:
            bbdrop._cached_master_key = original_cached

    @patch('keyring.get_password')
    def test_reads_master_key_from_keyring(self, mock_get):
        """Reads _master_key from keyring when not cached."""
        import bbdrop
        original_cached = bbdrop._cached_master_key
        try:
            bbdrop._cached_master_key = None
            mock_get.return_value = "keyring_master_key"
            result = bbdrop.get_encryption_key()
            assert result == "keyring_master_key"
            mock_get.assert_called_with("bbdrop", "_master_key")
        finally:
            bbdrop._cached_master_key = original_cached

    @patch('keyring.get_password', side_effect=Exception("No backend"))
    def test_raises_on_keyring_failure(self, mock_get):
        """Raises CredentialDecryptionError when keyring is unavailable."""
        import bbdrop
        original_cached = bbdrop._cached_master_key
        try:
            bbdrop._cached_master_key = None
            with pytest.raises(bbdrop.CredentialDecryptionError, match="OS keyring is not available"):
                bbdrop.get_encryption_key()
        finally:
            bbdrop._cached_master_key = original_cached

    @patch('bbdrop._migrate_encryption_keys')
    @patch('keyring.get_password', return_value=None)
    def test_triggers_migration_when_no_master_key(self, mock_get, mock_migrate):
        """Triggers migration when keyring has no _master_key entry."""
        import bbdrop
        original_cached = bbdrop._cached_master_key
        try:
            bbdrop._cached_master_key = None
            mock_migrate.return_value = "new_migrated_key"
            result = bbdrop.get_encryption_key()
            assert result == "new_migrated_key"
            mock_migrate.assert_called_once()
        finally:
            bbdrop._cached_master_key = original_cached


class TestCredentialStorageKeyringOnly:
    """Test that credential storage uses keyring only (no QSettings)."""

    @patch('keyring.set_password')
    def test_set_credential_stores_in_keyring(self, mock_set):
        """set_credential stores in keyring."""
        from bbdrop import set_credential
        set_credential('test_key', 'test_value')
        mock_set.assert_called_with("bbdrop", "test_key", "test_value")

    @patch('keyring.set_password')
    def test_set_credential_with_host_id(self, mock_set):
        """set_credential with host_id prefixes the key."""
        from bbdrop import set_credential
        set_credential('api_key', 'val', host_id='turbo')
        mock_set.assert_called_with("bbdrop", "turbo_api_key", "val")

    @patch('keyring.set_password', side_effect=Exception("Keyring broken"))
    def test_set_credential_raises_on_failure(self, mock_set):
        """set_credential raises CredentialDecryptionError on keyring failure."""
        from bbdrop import set_credential, CredentialDecryptionError
        with pytest.raises(CredentialDecryptionError, match="Failed to store credential"):
            set_credential('key', 'val')

    @patch('keyring.get_password', return_value='stored_value')
    def test_get_credential_reads_from_keyring(self, mock_get):
        """get_credential reads from keyring."""
        from bbdrop import get_credential
        result = get_credential('test_key')
        assert result == 'stored_value'
        mock_get.assert_called_with("bbdrop", "test_key")

    @patch('keyring.get_password', return_value=None)
    def test_get_credential_returns_empty_when_not_found(self, mock_get):
        """get_credential returns empty string when key not in keyring."""
        from bbdrop import get_credential
        result = get_credential('nonexistent')
        assert result == ""

    @patch('keyring.delete_password')
    def test_remove_credential_deletes_from_keyring(self, mock_del):
        """remove_credential deletes from keyring."""
        from bbdrop import remove_credential
        remove_credential('test_key')
        mock_del.assert_called_with("bbdrop", "test_key")


class TestMigrateEncryptionKeys:
    """Test the one-time encryption key migration."""

    def _make_legacy_encrypted(self, plaintext):
        """Encrypt a value with the legacy SHA-256 key for test setup."""
        from bbdrop import _get_legacy_encryption_key
        key = _get_legacy_encryption_key()
        f = Fernet(key)
        return f.encrypt(plaintext.encode()).decode()

    @patch('keyring.set_password')
    @patch('keyring.get_password', return_value=None)
    def test_migration_generates_and_stores_master_key(self, mock_get, mock_set):
        """Migration generates a new CSPRNG key and stores it in keyring."""
        from bbdrop import _migrate_encryption_keys

        with patch('PyQt6.QtCore.QSettings') as MockQSettings:
            mock_qs = MagicMock()
            mock_qs.allKeys.return_value = []
            mock_qs.value.return_value = ""
            MockQSettings.return_value = mock_qs

            new_key = _migrate_encryption_keys()

        # Verify the key is valid Fernet
        Fernet(new_key)

        # Verify master key was stored in keyring
        master_key_calls = [c for c in mock_set.call_args_list
                           if c == call("bbdrop", "_master_key", new_key)]
        assert len(master_key_calls) == 1

    @patch('keyring.set_password')
    @patch('keyring.get_password')
    def test_migration_re_encrypts_credentials(self, mock_get, mock_set):
        """Migration decrypts with old key and re-encrypts with new key."""
        from bbdrop import _migrate_encryption_keys

        # Create a value encrypted with the legacy key
        old_encrypted = self._make_legacy_encrypted("my_secret_password")

        # Mock keyring: return old encrypted value for 'password'
        def keyring_get(service, key):
            if key == 'password':
                return old_encrypted
            return None
        mock_get.side_effect = keyring_get

        with patch('PyQt6.QtCore.QSettings') as MockQSettings:
            mock_qs = MagicMock()
            mock_qs.allKeys.return_value = []
            mock_qs.value.return_value = ""
            MockQSettings.return_value = mock_qs

            new_key = _migrate_encryption_keys()

        # Find the set_credential call for 'password'
        password_calls = [c for c in mock_set.call_args_list
                         if c[0][1] == 'password']
        assert len(password_calls) == 1

        # Verify the re-encrypted value decrypts correctly with the new key
        new_encrypted = password_calls[0][0][2]
        new_fernet = Fernet(new_key)
        decrypted = new_fernet.decrypt(new_encrypted.encode()).decode()
        assert decrypted == "my_secret_password"

    @patch('keyring.set_password')
    @patch('keyring.get_password')
    def test_migration_preserves_plaintext_usernames(self, mock_get, mock_set):
        """Migration copies plaintext username values as-is."""
        def keyring_get(service, key):
            if key == 'username':
                return 'myuser'
            return None
        mock_get.side_effect = keyring_get

        with patch('PyQt6.QtCore.QSettings') as MockQSettings:
            mock_qs = MagicMock()
            mock_qs.allKeys.return_value = []
            mock_qs.value.return_value = ""
            MockQSettings.return_value = mock_qs

            _result = __import__('bbdrop')._migrate_encryption_keys()

        # Username should be stored as-is
        username_calls = [c for c in mock_set.call_args_list
                         if c[0][1] == 'username']
        assert len(username_calls) == 1
        assert username_calls[0][0][2] == 'myuser'

    @patch('keyring.set_password')
    @patch('keyring.get_password')
    def test_migration_skips_corrupted_values(self, mock_get, mock_set):
        """Corrupted values that can't be decrypted are copied as-is, not fatal."""
        def keyring_get(service, key):
            if key == 'password':
                return 'totally_not_fernet_data'
            return None
        mock_get.side_effect = keyring_get

        with patch('PyQt6.QtCore.QSettings') as MockQSettings:
            mock_qs = MagicMock()
            mock_qs.allKeys.return_value = []
            mock_qs.value.return_value = ""
            MockQSettings.return_value = mock_qs

            # Should not raise
            new_key = _result = __import__('bbdrop')._migrate_encryption_keys()

        # Value should be stored as-is (corrupted, but not lost)
        password_calls = [c for c in mock_set.call_args_list
                         if c[0][1] == 'password']
        assert len(password_calls) == 1
        assert password_calls[0][0][2] == 'totally_not_fernet_data'

    @patch('keyring.set_password')
    @patch('keyring.get_password')
    def test_migration_cleans_qsettings(self, mock_get, mock_set):
        """Migration removes all QSettings Credentials entries."""
        mock_get.return_value = None

        with patch('PyQt6.QtCore.QSettings') as MockQSettings:
            mock_qs = MagicMock()
            mock_qs.allKeys.return_value = ['password', 'api_key']
            mock_qs.value.return_value = ""
            MockQSettings.return_value = mock_qs

            __import__('bbdrop')._migrate_encryption_keys()

        # QSettings should have had remove called and sync called
        mock_qs.remove.assert_called()
        mock_qs.sync.assert_called()

    @patch('keyring.get_password')
    def test_migration_idempotent_via_master_key_check(self, mock_get):
        """When master key exists, get_encryption_key returns it — migration never runs."""
        import bbdrop
        original_cached = bbdrop._cached_master_key
        try:
            bbdrop._cached_master_key = None
            mock_get.return_value = "existing_master_key"

            with patch('bbdrop._migrate_encryption_keys') as mock_migrate:
                result = bbdrop.get_encryption_key()

            assert result == "existing_master_key"
            mock_migrate.assert_not_called()
        finally:
            bbdrop._cached_master_key = original_cached
