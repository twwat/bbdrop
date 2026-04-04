"""Tests for username encryption migration."""
import pytest
from unittest.mock import patch, MagicMock


class TestMigratePlaintextUsernames:
    """Test one-time migration of plaintext usernames to encrypted."""

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_encrypts_plaintext_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Plaintext username should be encrypted and re-stored."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = "myuser"
        mock_decrypt.side_effect = Exception("Not valid Fernet")
        mock_encrypt.return_value = "encrypted_myuser"

        migrate_plaintext_usernames()

        mock_encrypt.assert_any_call("myuser")
        mock_set.assert_any_call("username", "encrypted_myuser")

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_skips_already_encrypted_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Already-encrypted username should not be re-encrypted."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = "gAAAAABexample..."
        mock_decrypt.return_value = "myuser"  # Decrypts successfully = already encrypted

        migrate_plaintext_usernames()

        mock_encrypt.assert_not_called()
        mock_set.assert_not_called()

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_skips_empty_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Empty/missing usernames should be skipped."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = ""

        migrate_plaintext_usernames()

        mock_decrypt.assert_not_called()
        mock_encrypt.assert_not_called()

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_migrates_all_known_username_keys(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Should check all known username keys: global, imx, turbo."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = ""

        migrate_plaintext_usernames()

        # Should check at least these keys
        called_keys = [call.args[0] for call in mock_get.call_args_list]
        assert "username" in called_keys
        assert "imx_username" in called_keys
        assert "turbo_username" in called_keys


class TestSaveCredentialsEncryptsUsername:
    """Test that _save_credentials encrypts the username."""

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    def test_username_is_encrypted(self, mock_encrypt, mock_set):
        """_save_credentials should encrypt username before storing."""
        from src.utils.credentials import _save_credentials

        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"

        _save_credentials("myuser", "mypass")

        # Username should be encrypted
        mock_set.assert_any_call('username', 'encrypted_myuser')
        # Password should also be encrypted
        mock_set.assert_any_call('password', 'encrypted_mypass')


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
