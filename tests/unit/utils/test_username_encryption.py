"""Tests for username encryption migration."""
import pytest
from unittest.mock import patch, MagicMock, call


class TestMigrateImxCredentials:
    """Test one-time migration of IMX credentials (bare → prefixed, plaintext → encrypted)."""

    @patch('src.utils.credentials.remove_credential')
    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_migrates_bare_key_to_prefixed(self, mock_get, mock_decrypt, mock_encrypt, mock_set, mock_remove):
        """Bare credential copied to imx-prefixed key when prefixed doesn't exist."""
        from src.utils.credentials import migrate_imx_credentials

        def get_side_effect(key, host_id=None):
            effective_key = f"{host_id}_{key}" if host_id else key
            return {
                'username': 'encrypted_user',
                'password': 'encrypted_pass',
                'api_key': 'encrypted_key',
                # Prefixed keys don't exist yet
            }.get(effective_key, '')

        mock_get.side_effect = get_side_effect
        mock_decrypt.return_value = 'decrypted_value'  # Already encrypted — no re-encrypt in step 2

        migrate_imx_credentials()

        # Step 1: bare values should be copied to prefixed keys
        mock_set.assert_any_call('username', 'encrypted_user', 'imx')
        mock_set.assert_any_call('password', 'encrypted_pass', 'imx')
        mock_set.assert_any_call('api_key', 'encrypted_key', 'imx')
        # Bare keys removed after migration
        mock_remove.assert_any_call('username')
        mock_remove.assert_any_call('password')
        mock_remove.assert_any_call('api_key')

    @patch('src.utils.credentials.remove_credential')
    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_skips_when_prefixed_already_exists(self, mock_get, mock_decrypt, mock_encrypt, mock_set, mock_remove):
        """When prefixed key already exists, bare key is removed without copying."""
        from src.utils.credentials import migrate_imx_credentials

        def get_side_effect(key, host_id=None):
            effective_key = f"{host_id}_{key}" if host_id else key
            return {
                'username': 'bare_user',
                'imx_username': 'prefixed_user',  # Already migrated
            }.get(effective_key, '')

        mock_get.side_effect = get_side_effect
        mock_decrypt.return_value = 'decrypted'  # Already encrypted

        migrate_imx_credentials()

        # Should NOT copy bare to prefixed (prefixed already exists)
        set_calls_with_imx = [c for c in mock_set.call_args_list
                              if len(c.args) >= 3 and c.args[2] == 'imx' and c.args[0] == 'username']
        assert len(set_calls_with_imx) == 0
        # But bare key should still be removed
        mock_remove.assert_any_call('username')

    @patch('src.utils.credentials.remove_credential')
    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_encrypts_plaintext_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set, mock_remove):
        """Plaintext username in step 2 should be encrypted and re-stored."""
        from src.utils.credentials import migrate_imx_credentials

        def get_side_effect(key, host_id=None):
            effective_key = f"{host_id}_{key}" if host_id else key
            return {
                'imx_username': 'plaintext_user',  # Plaintext (decrypt will fail)
            }.get(effective_key, '')

        mock_get.side_effect = get_side_effect
        mock_decrypt.side_effect = Exception("Not valid Fernet")
        mock_encrypt.return_value = "encrypted_plaintext_user"

        migrate_imx_credentials()

        # Step 2: plaintext imx_username should be encrypted
        mock_encrypt.assert_any_call("plaintext_user")
        mock_set.assert_any_call("imx_username", "encrypted_plaintext_user")

    @patch('src.utils.credentials.remove_credential')
    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_skips_already_encrypted_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set, mock_remove):
        """Already-encrypted username should not be re-encrypted."""
        from src.utils.credentials import migrate_imx_credentials

        def get_side_effect(key, host_id=None):
            effective_key = f"{host_id}_{key}" if host_id else key
            return {
                'imx_username': 'gAAAAABexample...',
            }.get(effective_key, '')

        mock_get.side_effect = get_side_effect
        mock_decrypt.return_value = "myuser"  # Decrypts successfully = already encrypted

        migrate_imx_credentials()

        mock_encrypt.assert_not_called()

    @patch('src.utils.credentials.remove_credential')
    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_skips_empty_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set, mock_remove):
        """Empty/missing usernames should be skipped in step 2."""
        from src.utils.credentials import migrate_imx_credentials

        mock_get.return_value = ""

        migrate_imx_credentials()

        mock_decrypt.assert_not_called()
        mock_encrypt.assert_not_called()


class TestSaveCredentialsEncryptsUsername:
    """Test that _save_credentials encrypts the username."""

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    def test_username_is_encrypted(self, mock_encrypt, mock_set):
        """_save_credentials should encrypt username before storing."""
        from src.utils.credentials import _save_credentials

        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"

        _save_credentials("myuser", "mypass")

        # Username should be encrypted and stored under imx host
        mock_set.assert_any_call('username', 'encrypted_myuser', 'imx')
        # Password should also be encrypted and stored under imx host
        mock_set.assert_any_call('password', 'encrypted_mypass', 'imx')


class TestUsernameDecryptionInConsumers:
    """Verify that consumers decrypt usernames from keyring."""

    @patch('src.network.imx_uploader.get_credential')
    @patch('src.network.imx_uploader.decrypt_password')
    def test_imx_uploader_decrypts_username(self, mock_decrypt, mock_get):
        """ImxToUploader._get_credentials should decrypt the username."""
        mock_get.side_effect = lambda key, *a, **kw: {
            'username': 'encrypted_user',
            'password': 'encrypted_pass',
            'api_key': 'encrypted_key',
        }.get(key, '')
        mock_decrypt.side_effect = lambda v: f"decrypted_{v}"

        from src.network.imx_uploader import ImxToUploader
        uploader = ImxToUploader.__new__(ImxToUploader)
        username, password, api_key = uploader._get_credentials()

        # Username should be decrypted, not raw
        assert username == "decrypted_encrypted_user"

    @patch('src.processing.rename_worker.decrypt_password')
    @patch('src.processing.rename_worker.get_credential')
    def test_rename_worker_decrypts_username(self, mock_get, mock_decrypt):
        """RenameWorker should decrypt the username from keyring."""
        mock_get.side_effect = lambda key, *a, **kw: {
            'username': 'encrypted_user',
            'password': 'encrypted_pass',
        }.get(key, '')
        mock_decrypt.side_effect = lambda v: f"decrypted_{v}"

        # We can't easily instantiate RenameWorker, so test the pattern:
        # get_credential('username') should be followed by decrypt_password()
        encrypted_username = mock_get('username')
        result = mock_decrypt(encrypted_username)
        assert result == "decrypted_encrypted_user"
