"""Tests for dead-image ETag catalog and HEAD-request checker."""

import pytest
from unittest.mock import patch, Mock

from src.network.dead_image_etags import DEAD_IMAGE_ETAGS, is_dead_image_etag, check_thumbnail_head


class TestDeadImageEtagCatalog:
    """Verify the ETag catalog contents and lookup."""

    def test_catalog_is_frozenset(self):
        """Catalog should be a frozenset for O(1) lookup and immutability."""
        assert isinstance(DEAD_IMAGE_ETAGS, frozenset)

    def test_catalog_not_empty(self):
        """Catalog should contain known dead-image ETags."""
        assert len(DEAD_IMAGE_ETAGS) > 50

    def test_known_etag_matches(self):
        """Known dead-image ETag should be detected."""
        assert is_dead_image_etag('"65c43e4c-23a8"')

    def test_unknown_etag_does_not_match(self):
        """Random ETag should not match."""
        assert not is_dead_image_etag('"aaaa1111-bbbb"')

    def test_none_does_not_match(self):
        """None ETag should not match."""
        assert not is_dead_image_etag(None)

    def test_empty_string_does_not_match(self):
        """Empty string should not match."""
        assert not is_dead_image_etag('')


class TestCheckThumbnailHead:
    """Test the HEAD request helper function."""

    @patch('src.network.dead_image_etags.requests.head')
    def test_live_image_returns_online(self, mock_head):
        """Image with non-matching ETag should be reported as online."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {'ETag': '"aabbccdd-1234"'}
        mock_head.return_value = mock_resp

        result = check_thumbnail_head('https://example.com/thumb.jpg')
        assert result['status'] == 'online'
        assert result['url'] == 'https://example.com/thumb.jpg'

    @patch('src.network.dead_image_etags.requests.head')
    def test_dead_etag_returns_offline(self, mock_head):
        """Image with dead-image ETag should be reported as offline."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {'ETag': '"65c43e4c-23a8"'}
        mock_head.return_value = mock_resp

        result = check_thumbnail_head('https://example.com/thumb.jpg')
        assert result['status'] == 'offline'

    @patch('src.network.dead_image_etags.requests.head')
    def test_404_returns_offline(self, mock_head):
        """HTTP 404 should be reported as offline."""
        mock_resp = Mock()
        mock_resp.status_code = 404
        mock_resp.headers = {}
        mock_head.return_value = mock_resp

        result = check_thumbnail_head('https://example.com/thumb.jpg')
        assert result['status'] == 'offline'

    @patch('src.network.dead_image_etags.requests.head')
    def test_no_etag_header_returns_online(self, mock_head):
        """HTTP 200 with no ETag at all should be treated as online."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_head.return_value = mock_resp

        result = check_thumbnail_head('https://example.com/thumb.jpg')
        assert result['status'] == 'online'

    @patch('src.network.dead_image_etags.requests.head')
    def test_connection_error_returns_error(self, mock_head):
        """Network error should be reported as error."""
        import requests
        mock_head.side_effect = requests.ConnectionError("refused")

        result = check_thumbnail_head('https://example.com/thumb.jpg')
        assert result['status'] == 'error'
        assert 'error' in result

    @patch('src.network.dead_image_etags.requests.head')
    def test_timeout_returns_error(self, mock_head):
        """Timeout should be reported as error."""
        import requests
        mock_head.side_effect = requests.Timeout("timed out")

        result = check_thumbnail_head('https://example.com/thumb.jpg')
        assert result['status'] == 'error'
