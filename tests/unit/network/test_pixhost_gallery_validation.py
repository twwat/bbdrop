"""Test Pixhost gallery creation validation (gallery_upload_hash)."""

import json
import pytest
from unittest.mock import patch, MagicMock

from src.network.pixhost_client import PixhostClient


@pytest.fixture
def pixhost_client():
    with patch('src.core.image_host_config.get_image_host_config_manager') as mock_mgr:
        yield PixhostClient()


def test_pixhost_create_gallery_missing_gallery_upload_hash(pixhost_client):
    """Test that create_gallery raises RuntimeError when gallery_upload_hash is missing."""
    with patch('pycurl.Curl') as mock_curl_class:
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl

        mock_curl.getinfo.return_value = 200

        def mock_perform():
            # Simulate API response WITH gallery_hash but WITHOUT gallery_upload_hash
            for call in mock_curl.setopt.call_args_list:
                if call[0][0] == 10001:  # pycurl.WRITEDATA
                    buffer = call[0][1]
                    buffer.write(json.dumps({
                        'gallery_hash': 'hash123',
                        # gallery_upload_hash is intentionally missing
                    }).encode('utf-8'))
                    break
        mock_curl.perform.side_effect = mock_perform

        # Should raise RuntimeError, not silently fail
        with pytest.raises(RuntimeError, match="Could not find gallery_upload_hash in response"):
            pixhost_client.create_gallery('Test Gallery')


def test_pixhost_create_gallery_missing_gallery_hash(pixhost_client):
    """Test that create_gallery raises RuntimeError when gallery_hash is missing."""
    with patch('pycurl.Curl') as mock_curl_class:
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl

        mock_curl.getinfo.return_value = 200

        def mock_perform():
            # Simulate API response without gallery_hash
            for call in mock_curl.setopt.call_args_list:
                if call[0][0] == 10001:  # pycurl.WRITEDATA
                    buffer = call[0][1]
                    buffer.write(json.dumps({
                        'gallery_upload_hash': 'upload_hash123',
                        # gallery_hash is intentionally missing
                    }).encode('utf-8'))
                    break
        mock_curl.perform.side_effect = mock_perform

        # Should raise RuntimeError for missing gallery_hash
        with pytest.raises(RuntimeError, match="Could not find gallery_hash in response"):
            pixhost_client.create_gallery('Test Gallery')


def test_pixhost_create_gallery_both_hashes_present(pixhost_client):
    """Test that create_gallery succeeds when both hashes are present."""
    with patch('pycurl.Curl') as mock_curl_class:
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl

        mock_curl.getinfo.return_value = 200

        def mock_perform():
            # Simulate normal API response with both hashes
            for call in mock_curl.setopt.call_args_list:
                if call[0][0] == 10001:  # pycurl.WRITEDATA
                    buffer = call[0][1]
                    buffer.write(json.dumps({
                        'gallery_hash': 'hash456',
                        'gallery_upload_hash': 'upload_hash456'
                    }).encode('utf-8'))
                    break
        mock_curl.perform.side_effect = mock_perform

        # Should succeed and return gallery_hash
        result = pixhost_client.create_gallery('Test Gallery')

        assert result == 'hash456'
        assert pixhost_client._gallery_hash == 'hash456'
        assert pixhost_client._gallery_upload_hash == 'upload_hash456'
