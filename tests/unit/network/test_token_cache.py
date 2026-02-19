"""
Comprehensive pytest test suite for token cache management.

Tests token storage, retrieval, expiration, and invalidation
with QSettings mocking and proper encryption handling.
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QSettings

from src.network.token_cache import TokenCache, get_token_cache


class TestTokenCache:
    """Test suite for TokenCache class."""

    @pytest.fixture
    def mock_settings(self):
        """Create a mock QSettings object."""
        settings = MagicMock(spec=QSettings)
        settings._data = {}  # Internal storage for mocked settings
        settings._groups = []  # Track group hierarchy

        def mock_begin_group(group):
            settings._groups.append(group)

        def mock_end_group():
            if settings._groups:
                settings._groups.pop()

        def mock_set_value(key, value):
            full_key = "/".join(settings._groups + [key])
            settings._data[full_key] = value

        def mock_value(key, default=None):
            full_key = "/".join(settings._groups + [key])
            return settings._data.get(full_key, default)

        def mock_remove(key):
            if key == "":  # Remove all keys in current group
                prefix = "/".join(settings._groups)
                keys_to_remove = [k for k in settings._data if k.startswith(prefix)]
                for k in keys_to_remove:
                    del settings._data[k]
            else:
                full_key = "/".join(settings._groups + [key])
                settings._data.pop(full_key, None)

        settings.beginGroup = mock_begin_group
        settings.endGroup = mock_end_group
        settings.setValue = mock_set_value
        settings.value = mock_value
        settings.remove = mock_remove

        return settings

    @pytest.fixture
    def token_cache(self, mock_settings):
        """Create TokenCache instance with mocked QSettings."""
        with patch('src.network.token_cache.QSettings', return_value=mock_settings):
            cache = TokenCache()
        return cache

    @pytest.fixture
    def mock_encryption(self):
        """Mock encryption/decryption functions."""
        with patch('src.network.token_cache.encrypt_password') as mock_encrypt, \
             patch('src.network.token_cache.decrypt_password') as mock_decrypt:
            mock_encrypt.side_effect = lambda x: f"encrypted_{x}"
            mock_decrypt.side_effect = lambda x: x.replace("encrypted_", "")
            yield mock_encrypt, mock_decrypt

    def test_store_token_without_ttl(self, token_cache, mock_encryption):
        """Test storing token without expiration."""
        mock_encrypt, _ = mock_encryption

        token_cache.store_token("rapidgator", "test_token_123", ttl=None)

        # Verify encryption was called
        mock_encrypt.assert_called_once_with("test_token_123")

        # Verify data stored correctly
        settings = token_cache.settings
        assert settings._data['FileHosts/Tokens/rapidgator/token'] == 'encrypted_test_token_123'
        assert settings._data['FileHosts/Tokens/rapidgator/cached_at'] == pytest.approx(time.time(), abs=2)
        assert 'FileHosts/Tokens/rapidgator/expires_at' not in settings._data

    def test_store_token_with_ttl(self, token_cache, mock_encryption):
        """Test storing token with TTL expiration."""
        ttl = 3600  # 1 hour
        expected_expiry = int(time.time()) + ttl

        token_cache.store_token("k2s", "api_key_xyz", ttl=ttl)

        settings = token_cache.settings
        assert 'FileHosts/Tokens/k2s/expires_at' in settings._data
        stored_expiry = settings._data['FileHosts/Tokens/k2s/expires_at']
        assert stored_expiry == pytest.approx(expected_expiry, abs=2)

    def test_get_token_valid(self, token_cache, mock_encryption):
        """Test retrieving a valid non-expired token."""
        # Store token
        token_cache.store_token("gofile", "valid_token", ttl=3600)

        # Retrieve token
        retrieved = token_cache.get_token("gofile")

        assert retrieved == "valid_token"

    def test_get_token_expired(self, token_cache, mock_encryption):
        """Test that expired tokens return None and are cleared."""
        # Store token that expires immediately
        token_cache.store_token("katfile", "expired_token", ttl=-1)

        # Wait a moment to ensure expiry
        time.sleep(0.1)

        # Try to retrieve - should return None
        retrieved = token_cache.get_token("katfile")

        assert retrieved is None
        # Verify token was cleared
        assert 'FileHosts/Tokens/katfile/token' not in token_cache.settings._data

    def test_get_token_not_found(self, token_cache, mock_encryption):
        """Test retrieving token that doesn't exist."""
        retrieved = token_cache.get_token("nonexistent_host")

        assert retrieved is None

    def test_get_token_decryption_failure(self, token_cache, mock_settings):
        """Test handling of decryption failures."""
        # Store encrypted token directly
        mock_settings._groups = ['FileHosts', 'Tokens', 'corrupted_host']
        mock_settings.setValue('token', 'corrupted_encrypted_data')
        mock_settings._groups = []

        with patch('src.network.token_cache.decrypt_password') as mock_decrypt:
            mock_decrypt.side_effect = Exception("Decryption failed")

            retrieved = token_cache.get_token("corrupted_host")

            assert retrieved is None
            # Verify token was cleared after decryption failure
            assert 'FileHosts/Tokens/corrupted_host/token' not in mock_settings._data

    def test_clear_token(self, token_cache, mock_encryption):
        """Test clearing a specific host's token."""
        # Store token
        token_cache.store_token("pixeldrain", "token_to_clear", ttl=3600)

        # Verify stored
        assert token_cache.get_token("pixeldrain") == "token_to_clear"

        # Clear token
        token_cache.clear_token("pixeldrain")

        # Verify cleared
        assert token_cache.get_token("pixeldrain") is None
        assert 'FileHosts/Tokens/pixeldrain/token' not in token_cache.settings._data

    def test_clear_nonexistent_token(self, token_cache):
        """Test clearing token that doesn't exist (should not error)."""
        token_cache.clear_token("nonexistent_host")
        # Should complete without error

    def test_get_token_info_valid(self, token_cache, mock_encryption):
        """Test getting information about a valid token."""
        ttl = 3600
        before_time = int(time.time())
        token_cache.store_token("filehost", "info_token", ttl=ttl)
        after_time = int(time.time()) + 1  # Add 1 second buffer

        info = token_cache.get_token_info("filehost")

        assert info is not None
        assert info['is_valid'] is True
        assert info['cached_at'] >= before_time
        assert info['cached_at'] <= after_time
        assert info['expires_at'] == pytest.approx(before_time + ttl, abs=3)
        assert info['ttl_remaining'] > 0
        assert info['ttl_remaining'] <= ttl

    def test_get_token_info_expired(self, token_cache, mock_encryption):
        """Test getting information about an expired token."""
        # Store token with negative TTL (already expired)
        token_cache.store_token("expired_host", "expired_token", ttl=-10)

        info = token_cache.get_token_info("expired_host")

        assert info is not None
        assert info['is_valid'] is False
        assert info['ttl_remaining'] == 0

    def test_get_token_info_no_expiration(self, token_cache, mock_encryption):
        """Test getting information about token without expiration."""
        token_cache.store_token("permanent_host", "permanent_token", ttl=None)

        info = token_cache.get_token_info("permanent_host")

        assert info is not None
        assert info['is_valid'] is True
        assert info['expires_at'] is None
        assert info['ttl_remaining'] is None

    def test_get_token_info_not_found(self, token_cache):
        """Test getting info for non-existent token."""
        info = token_cache.get_token_info("missing_host")

        assert info is None

    def test_clear_all_tokens(self, token_cache, mock_encryption):
        """Test clearing all cached tokens."""
        # Store multiple tokens
        token_cache.store_token("host1", "token1", ttl=3600)
        token_cache.store_token("host2", "token2", ttl=7200)
        token_cache.store_token("host3", "token3", ttl=None)

        # Verify stored
        assert token_cache.get_token("host1") == "token1"
        assert token_cache.get_token("host2") == "token2"
        assert token_cache.get_token("host3") == "token3"

        # Clear all
        token_cache.clear_all_tokens()

        # Verify all cleared
        assert token_cache.get_token("host1") is None
        assert token_cache.get_token("host2") is None
        assert token_cache.get_token("host3") is None

    def test_store_overwrites_existing_token(self, token_cache, mock_encryption):
        """Test that storing a new token overwrites the old one."""
        # Store initial token
        token_cache.store_token("host", "old_token", ttl=3600)
        assert token_cache.get_token("host") == "old_token"

        # Overwrite with new token
        token_cache.store_token("host", "new_token", ttl=7200)
        assert token_cache.get_token("host") == "new_token"

        # Verify old token is gone
        info = token_cache.get_token_info("host")
        # TTL should be for new token (7200s)
        assert info['ttl_remaining'] > 3600

    def test_ttl_countdown_accuracy(self, token_cache, mock_encryption):
        """Test that TTL countdown is accurate over time."""
        ttl = 10  # 10 seconds
        token_cache.store_token("countdown_host", "test_token", ttl=ttl)

        # Immediate check
        info1 = token_cache.get_token_info("countdown_host")
        remaining1 = info1['ttl_remaining']
        assert remaining1 <= ttl

        # Wait 2 seconds
        time.sleep(2)

        # Check again
        info2 = token_cache.get_token_info("countdown_host")
        remaining2 = info2['ttl_remaining']

        # Remaining should be approximately 2 seconds less
        assert remaining2 < remaining1
        assert abs((remaining1 - remaining2) - 2) <= 5  # Allow 5s tolerance for test overhead

    def test_concurrent_token_storage(self, mock_encryption):
        """Test storing tokens for multiple hosts concurrently."""
        with patch('src.network.token_cache.QSettings') as mock_qsettings:
            mock_settings = MagicMock()
            mock_settings._data = {}
            mock_settings._groups = []

            def mock_begin_group(group):
                mock_settings._groups.append(group)

            def mock_end_group():
                if mock_settings._groups:
                    mock_settings._groups.pop()

            def mock_set_value(key, value):
                full_key = "/".join(mock_settings._groups + [key])
                mock_settings._data[full_key] = value

            mock_settings.beginGroup = mock_begin_group
            mock_settings.endGroup = mock_end_group
            mock_settings.setValue = mock_set_value

            mock_qsettings.return_value = mock_settings

            cache = TokenCache()

            # Store tokens for multiple hosts
            cache.store_token("host_a", "token_a", ttl=3600)
            cache.store_token("host_b", "token_b", ttl=7200)
            cache.store_token("host_c", "token_c", ttl=None)

            # Verify all tokens stored independently
            assert 'FileHosts/Tokens/host_a/token' in mock_settings._data
            assert 'FileHosts/Tokens/host_b/token' in mock_settings._data
            assert 'FileHosts/Tokens/host_c/token' in mock_settings._data

    def test_malformed_expiry_handling(self, token_cache, mock_settings):
        """Test handling of malformed expiry timestamps."""
        # Manually inject malformed data
        mock_settings._groups = ['FileHosts', 'Tokens', 'malformed_host']
        mock_settings.setValue('token', 'encrypted_token')
        mock_settings.setValue('expires_at', 'not_a_number')  # Malformed
        mock_settings.setValue('cached_at', int(time.time()))
        mock_settings._groups = []

        with patch('src.network.token_cache.decrypt_password', return_value='decrypted_token'):
            # Should handle malformed expiry gracefully (treat as no expiry)
            retrieved = token_cache.get_token("malformed_host")

            # Token should still be retrieved despite malformed expiry
            assert retrieved == 'decrypted_token'


class TestGetTokenCacheGlobal:
    """Test suite for global token cache singleton."""

    def test_get_token_cache_singleton(self):
        """Test that get_token_cache returns singleton instance."""
        with patch('src.network.token_cache.QSettings'):
            cache1 = get_token_cache()
            cache2 = get_token_cache()

            assert cache1 is cache2

    def test_get_token_cache_creates_instance(self):
        """Test that get_token_cache creates instance on first call."""
        # Reset global instance
        import src.network.token_cache
        src.network.token_cache._token_cache = None

        with patch('src.network.token_cache.QSettings'):
            cache = get_token_cache()

            assert cache is not None
            assert isinstance(cache, TokenCache)

        # Cleanup
        src.network.token_cache._token_cache = None


class TestTokenCacheEdgeCases:
    """Test suite for edge cases and boundary conditions."""

    @pytest.fixture
    def mock_settings(self):
        """Create a mock QSettings object."""
        settings = MagicMock(spec=QSettings)
        settings._data = {}  # Internal storage for mocked settings
        settings._groups = []  # Track group hierarchy

        def mock_begin_group(group):
            settings._groups.append(group)

        def mock_end_group():
            if settings._groups:
                settings._groups.pop()

        def mock_set_value(key, value):
            full_key = "/".join(settings._groups + [key])
            settings._data[full_key] = value

        def mock_value(key, default=None):
            full_key = "/".join(settings._groups + [key])
            return settings._data.get(full_key, default)

        def mock_remove(key):
            if key == "":  # Remove all keys in current group
                prefix = "/".join(settings._groups)
                keys_to_remove = [k for k in settings._data if k.startswith(prefix)]
                for k in keys_to_remove:
                    del settings._data[k]
            else:
                full_key = "/".join(settings._groups + [key])
                settings._data.pop(full_key, None)

        settings.beginGroup = mock_begin_group
        settings.endGroup = mock_end_group
        settings.setValue = mock_set_value
        settings.value = mock_value
        settings.remove = mock_remove

        return settings

    @pytest.fixture
    def token_cache(self, mock_settings):
        """Create TokenCache instance with mocked QSettings."""
        with patch('src.network.token_cache.QSettings', return_value=mock_settings):
            cache = TokenCache()
        return cache

    @pytest.fixture
    def mock_encryption(self):
        """Mock encryption/decryption functions."""
        with patch('src.network.token_cache.encrypt_password') as mock_encrypt, \
             patch('src.network.token_cache.decrypt_password') as mock_decrypt:
            mock_encrypt.side_effect = lambda x: f"encrypted_{x}"
            mock_decrypt.side_effect = lambda x: x.replace("encrypted_", "")
            yield mock_encrypt, mock_decrypt

    def test_store_empty_token(self, token_cache, mock_encryption):
        """Test storing empty string as token."""
        token_cache.store_token("empty_host", "", ttl=3600)

        retrieved = token_cache.get_token("empty_host")

        assert retrieved == ""

    def test_store_very_long_token(self, token_cache, mock_encryption):
        """Test storing very long token string."""
        long_token = "a" * 10000  # 10KB token
        token_cache.store_token("long_host", long_token, ttl=3600)

        retrieved = token_cache.get_token("long_host")

        assert retrieved == long_token

    def test_store_special_characters_in_token(self, token_cache, mock_encryption):
        """Test storing token with special characters."""
        special_token = "token_!@#$%^&*()_+{}[]|\\:\";<>?,./"
        token_cache.store_token("special_host", special_token, ttl=3600)

        retrieved = token_cache.get_token("special_host")

        assert retrieved == special_token

    def test_store_unicode_token(self, token_cache, mock_encryption):
        """Test storing token with unicode characters."""
        unicode_token = "token_日本語_العربية_🔒"
        token_cache.store_token("unicode_host", unicode_token, ttl=3600)

        retrieved = token_cache.get_token("unicode_host")

        assert retrieved == unicode_token

    def test_host_id_with_special_characters(self, token_cache, mock_encryption):
        """Test storing token with special characters in host ID."""
        host_id = "host-with-dashes_and_underscores.com"
        token_cache.store_token(host_id, "test_token", ttl=3600)

        retrieved = token_cache.get_token(host_id)

        assert retrieved == "test_token"

    def test_zero_ttl(self, token_cache, mock_encryption):
        """Test storing token with zero TTL (expires immediately)."""
        token_cache.store_token("zero_ttl_host", "token", ttl=0)

        # Should expire immediately
        retrieved = token_cache.get_token("zero_ttl_host")

        assert retrieved is None

    def test_negative_ttl(self, token_cache, mock_encryption):
        """Test storing token with negative TTL (already expired)."""
        token_cache.store_token("negative_ttl_host", "token", ttl=-3600)

        # Should be expired
        retrieved = token_cache.get_token("negative_ttl_host")

        assert retrieved is None

    def test_very_large_ttl(self, token_cache, mock_encryption):
        """Test storing token with very large TTL (decades)."""
        ttl = 10 * 365 * 24 * 3600  # 10 years
        token_cache.store_token("long_ttl_host", "token", ttl=ttl)

        info = token_cache.get_token_info("long_ttl_host")

        assert info['is_valid'] is True
        assert info['ttl_remaining'] > 0
        assert info['ttl_remaining'] <= ttl
