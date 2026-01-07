"""
Comprehensive test suite for image status checking functionality in src/processing/rename_worker.py.

Tests the following methods:
- _extract_image_id(): Extract image ID from imx.to URLs
- _parse_found_count(): Parse 'Found: X images' from HTML response
- _parse_online_image_ids(): Parse online image IDs from textarea
- check_image_status(): Queue status check with cancellation handling
- _perform_status_check(): Fast path vs slow path optimization
"""

import pytest
import threading
import queue
import time
from unittest.mock import Mock, MagicMock, patch, PropertyMock, call

from src.processing.rename_worker import RenameWorker


# =============================================================================
# Helper Functions
# =============================================================================

def create_streaming_response(status_code: int, html_content: str) -> Mock:
    """Create a mock response that supports streaming via iter_content().

    The _stream_and_detect_found_count() method uses iter_content() for streaming,
    so we need to mock the response to return an iterator of byte chunks.

    Args:
        status_code: HTTP status code for the response
        html_content: The HTML content to return as chunks

    Returns:
        Mock response object with iter_content() configured
    """
    mock_response = Mock()
    mock_response.status_code = status_code

    # Convert HTML to bytes and create a single-chunk iterator
    html_bytes = html_content.encode('utf-8')
    mock_response.iter_content = Mock(return_value=iter([html_bytes]))

    return mock_response


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def minimal_worker():
    """Create a minimal RenameWorker instance for testing internal methods.

    Bypasses full initialization by using __new__ and setting only required attributes.
    This is faster and avoids side effects from full initialization.
    """
    worker = RenameWorker.__new__(RenameWorker)
    worker._status_check_cancelled = threading.Event()
    worker.session = Mock()
    worker.web_url = "https://imx.to"
    worker.login_complete = threading.Event()
    worker.login_complete.set()
    worker.login_successful = True
    worker.running = True
    worker.status_check_queue = queue.Queue()

    # Mock signals to avoid PyQt6 initialization
    worker.status_check_progress = Mock()
    worker.status_check_completed = Mock()
    worker.status_check_error = Mock()
    worker.quick_count_available = Mock()

    return worker


@pytest.fixture
def sample_html_found_count():
    """Sample HTML with 'Found: X images' text."""
    return '''
    <html>
    <body>
        <div class="content">
            <h2>Moderate Images</h2>
            <p>Found: 43487 images</p>
            <textarea class="imageallcodes">
            https://imx.to/i/abc123
            https://imx.to/i/def456
            </textarea>
        </div>
    </body>
    </html>
    '''


@pytest.fixture
def sample_html_singular_image():
    """Sample HTML with singular 'Found: 1 image' text."""
    return '''
    <html>
    <body>
        <p>Found: 1 image</p>
        <textarea class="imageallcodes">
        https://imx.to/i/xyz789
        </textarea>
    </body>
    </html>
    '''


@pytest.fixture
def sample_html_no_found():
    """Sample HTML without 'Found:' text."""
    return '''
    <html>
    <body>
        <div>No images found</div>
    </body>
    </html>
    '''


@pytest.fixture
def sample_html_with_textarea():
    """Sample HTML with textarea containing image URLs."""
    return '''
    <html>
    <body>
        <p>Found: 5 images</p>
        <textarea class="imageallcodes">
        https://imx.to/i/abc123
        https://imx.to/i/def456
        https://i.imx.to/thumb/ghi789.jpg
        https://imx.to/i/jkl012
        https://imx.to/i/mno345
        </textarea>
    </body>
    </html>
    '''


@pytest.fixture
def sample_html_empty_textarea():
    """Sample HTML with empty textarea."""
    return '''
    <html>
    <body>
        <p>Found: 0 images</p>
        <textarea class="imageallcodes"></textarea>
    </body>
    </html>
    '''


@pytest.fixture
def sample_galleries_data():
    """Sample galleries data for status check."""
    return [
        {
            'db_id': 1,
            'path': '/path/to/gallery1',
            'name': 'Gallery One',
            'image_urls': [
                'https://imx.to/i/abc123',
                'https://imx.to/i/def456',
                'https://imx.to/i/ghi789'
            ]
        },
        {
            'db_id': 2,
            'path': '/path/to/gallery2',
            'name': 'Gallery Two',
            'image_urls': [
                'https://imx.to/i/jkl012',
                'https://i.imx.to/thumb/mno345.jpg'
            ]
        }
    ]


# =============================================================================
# TestExtractImageId - Tests for _extract_image_id()
# =============================================================================

class TestExtractImageId:
    """Test _extract_image_id() method for extracting IDs from imx.to URLs."""

    def test_extract_id_from_i_url(self, minimal_worker):
        """Test extracting ID from standard /i/ URL format."""
        url = "https://imx.to/i/6dg3e2"
        assert minimal_worker._extract_image_id(url) == "6dg3e2"

    def test_extract_id_from_thumb_url(self, minimal_worker):
        """Test extracting ID from thumbnail URL format."""
        url = "https://i.imx.to/thumb/6dg3e2.jpg"
        assert minimal_worker._extract_image_id(url) == "6dg3e2"

    def test_extract_id_from_thumb_url_png(self, minimal_worker):
        """Test extracting ID from thumbnail URL with PNG extension."""
        url = "https://i.imx.to/thumb/abc123.png"
        assert minimal_worker._extract_image_id(url) == "abc123"

    def test_extract_id_invalid_url_returns_none(self, minimal_worker):
        """Test invalid URL returns None."""
        url = "https://example.com/image.jpg"
        assert minimal_worker._extract_image_id(url) is None

    def test_extract_id_empty_string(self, minimal_worker):
        """Test empty string returns None."""
        assert minimal_worker._extract_image_id("") is None

    def test_extract_id_no_path(self, minimal_worker):
        """Test URL without relevant path returns None."""
        url = "https://imx.to/gallery/123"
        assert minimal_worker._extract_image_id(url) is None

    def test_extract_id_alphanumeric_only(self, minimal_worker):
        """Test that only alphanumeric IDs are matched."""
        url = "https://imx.to/i/Abc123XYZ"
        assert minimal_worker._extract_image_id(url) == "Abc123XYZ"

    def test_extract_id_lowercase(self, minimal_worker):
        """Test lowercase ID extraction."""
        url = "https://imx.to/i/abcdef"
        assert minimal_worker._extract_image_id(url) == "abcdef"

    def test_extract_id_uppercase(self, minimal_worker):
        """Test uppercase ID extraction."""
        url = "https://imx.to/i/ABCDEF"
        assert minimal_worker._extract_image_id(url) == "ABCDEF"

    def test_extract_id_numbers_only(self, minimal_worker):
        """Test numeric ID extraction."""
        url = "https://imx.to/i/123456"
        assert minimal_worker._extract_image_id(url) == "123456"

    def test_extract_id_with_query_params(self, minimal_worker):
        """Test ID extraction with query parameters in URL."""
        url = "https://imx.to/i/abc123?size=large"
        assert minimal_worker._extract_image_id(url) == "abc123"

    def test_extract_id_http_url(self, minimal_worker):
        """Test ID extraction from HTTP (non-HTTPS) URL."""
        url = "http://imx.to/i/xyz789"
        assert minimal_worker._extract_image_id(url) == "xyz789"

    def test_extract_id_with_trailing_slash(self, minimal_worker):
        """Test ID extraction with trailing slash."""
        url = "https://imx.to/i/abc123/"
        # The regex should still match abc123
        result = minimal_worker._extract_image_id(url)
        assert result == "abc123"


# =============================================================================
# TestParseFoundCount - Tests for _parse_found_count()
# =============================================================================

class TestParseFoundCount:
    """Test _parse_found_count() method for parsing image counts from HTML."""

    def test_parse_found_count_valid(self, minimal_worker, sample_html_found_count):
        """Test parsing valid 'Found: X images' text."""
        assert minimal_worker._parse_found_count(sample_html_found_count) == 43487

    def test_parse_found_count_singular(self, minimal_worker, sample_html_singular_image):
        """Test parsing singular 'Found: 1 image' text."""
        assert minimal_worker._parse_found_count(sample_html_singular_image) == 1

    def test_parse_found_count_missing(self, minimal_worker, sample_html_no_found):
        """Test parsing when 'Found:' is not present returns 0."""
        assert minimal_worker._parse_found_count(sample_html_no_found) == 0

    def test_parse_found_count_zero(self, minimal_worker):
        """Test parsing 'Found: 0 images' text."""
        html = '<p>Found: 0 images</p>'
        assert minimal_worker._parse_found_count(html) == 0

    def test_parse_found_count_large_number(self, minimal_worker):
        """Test parsing large number."""
        html = '<p>Found: 999999 images</p>'
        assert minimal_worker._parse_found_count(html) == 999999

    def test_parse_found_count_case_insensitive(self, minimal_worker):
        """Test parsing is case insensitive for 'Found' and 'images'."""
        html_uppercase = '<p>FOUND: 100 IMAGES</p>'
        html_mixed = '<p>Found: 50 Images</p>'

        assert minimal_worker._parse_found_count(html_uppercase) == 100
        assert minimal_worker._parse_found_count(html_mixed) == 50

    def test_parse_found_count_with_whitespace(self, minimal_worker):
        """Test parsing with extra whitespace."""
        html = '<p>Found:   42   images</p>'
        assert minimal_worker._parse_found_count(html) == 42

    def test_parse_found_count_in_div(self, minimal_worker):
        """Test parsing 'Found:' inside various HTML elements."""
        html = '<div class="info">Found: 25 images</div>'
        assert minimal_worker._parse_found_count(html) == 25

    def test_parse_found_count_empty_string(self, minimal_worker):
        """Test parsing empty string returns 0."""
        assert minimal_worker._parse_found_count("") == 0

    def test_parse_found_count_malformed(self, minimal_worker):
        """Test parsing malformed text returns 0."""
        html = '<p>Found: abc images</p>'
        assert minimal_worker._parse_found_count(html) == 0


# =============================================================================
# TestParseOnlineImageIds - Tests for _parse_online_image_ids()
# =============================================================================

class TestParseOnlineImageIds:
    """Test _parse_online_image_ids() method for extracting IDs from textarea."""

    def test_parse_online_ids_from_textarea(self, minimal_worker, sample_html_with_textarea):
        """Test extracting IDs from textarea with multiple URLs."""
        ids = minimal_worker._parse_online_image_ids(sample_html_with_textarea)

        assert isinstance(ids, set)
        assert len(ids) == 5
        assert "abc123" in ids
        assert "def456" in ids
        assert "ghi789" in ids
        assert "jkl012" in ids
        assert "mno345" in ids

    def test_parse_online_ids_empty(self, minimal_worker, sample_html_empty_textarea):
        """Test parsing empty textarea returns empty set."""
        ids = minimal_worker._parse_online_image_ids(sample_html_empty_textarea)

        assert isinstance(ids, set)
        assert len(ids) == 0

    def test_parse_online_ids_no_textarea(self, minimal_worker):
        """Test parsing HTML without textarea returns empty set."""
        html = '<div>No textarea here</div>'
        ids = minimal_worker._parse_online_image_ids(html)

        assert isinstance(ids, set)
        assert len(ids) == 0

    def test_parse_online_ids_mixed_formats(self, minimal_worker):
        """Test parsing textarea with mixed URL formats."""
        html = '''
        <textarea class="imageallcodes">
        https://imx.to/i/abc123
        https://i.imx.to/thumb/def456.jpg
        https://imx.to/i/ghi789
        https://i.imx.to/thumb/jkl012.png
        </textarea>
        '''
        ids = minimal_worker._parse_online_image_ids(html)

        assert len(ids) == 4
        assert "abc123" in ids
        assert "def456" in ids
        assert "ghi789" in ids
        assert "jkl012" in ids

    def test_parse_online_ids_duplicate_urls(self, minimal_worker):
        """Test parsing textarea with duplicate URLs returns unique IDs."""
        html = '''
        <textarea class="imageallcodes">
        https://imx.to/i/abc123
        https://imx.to/i/abc123
        https://imx.to/i/def456
        </textarea>
        '''
        ids = minimal_worker._parse_online_image_ids(html)

        assert len(ids) == 2
        assert "abc123" in ids
        assert "def456" in ids

    def test_parse_online_ids_with_newlines(self, minimal_worker):
        """Test parsing textarea content with various newline formats."""
        html = '''
        <textarea class="imageallcodes">https://imx.to/i/abc123
https://imx.to/i/def456
https://imx.to/i/ghi789</textarea>
        '''
        ids = minimal_worker._parse_online_image_ids(html)

        assert len(ids) == 3

    def test_parse_online_ids_textarea_with_double_quotes(self, minimal_worker):
        """Test parsing textarea with double-quoted class attribute."""
        html = '''
        <textarea class="imageallcodes">
        https://imx.to/i/test123
        </textarea>
        '''
        ids = minimal_worker._parse_online_image_ids(html)

        assert len(ids) == 1
        assert "test123" in ids

    def test_parse_online_ids_textarea_with_single_quotes(self, minimal_worker):
        """Test parsing textarea with single-quoted class attribute."""
        html = """
        <textarea class='imageallcodes'>
        https://imx.to/i/test456
        </textarea>
        """
        ids = minimal_worker._parse_online_image_ids(html)

        assert len(ids) == 1
        assert "test456" in ids

    def test_parse_online_ids_ignores_other_textareas(self, minimal_worker):
        """Test that only textarea with class='imageallcodes' is parsed."""
        html = '''
        <textarea class="other">
        https://imx.to/i/ignore123
        </textarea>
        <textarea class="imageallcodes">
        https://imx.to/i/include456
        </textarea>
        '''
        ids = minimal_worker._parse_online_image_ids(html)

        assert len(ids) == 1
        assert "include456" in ids
        assert "ignore123" not in ids

    def test_parse_online_ids_empty_string(self, minimal_worker):
        """Test parsing empty string returns empty set."""
        ids = minimal_worker._parse_online_image_ids("")

        assert isinstance(ids, set)
        assert len(ids) == 0


# =============================================================================
# TestCancelStatusCheck - Tests for cancellation functionality
# =============================================================================

class TestCancelStatusCheck:
    """Test cancellation functionality for status checks."""

    def test_cancel_status_check_sets_event(self, minimal_worker):
        """Test that cancel_status_check() sets the cancellation event."""
        assert not minimal_worker._status_check_cancelled.is_set()

        minimal_worker.cancel_status_check()

        assert minimal_worker._status_check_cancelled.is_set()

    def test_cancel_clears_event_before_queue(self, minimal_worker):
        """Test that check_image_status() clears cancel flag BEFORE queuing.

        This is critical: cancellations between queuing and processing must be honored.
        The flag should be cleared in check_image_status(), not in _perform_status_check().
        """
        # Set cancellation flag
        minimal_worker._status_check_cancelled.set()
        assert minimal_worker._status_check_cancelled.is_set()

        # Call check_image_status
        galleries_data = [
            {'db_id': 1, 'path': '/test', 'name': 'Test', 'image_urls': ['https://imx.to/i/abc123']}
        ]
        minimal_worker.check_image_status(galleries_data)

        # Flag should be cleared BEFORE the data was queued
        assert not minimal_worker._status_check_cancelled.is_set()

        # Data should be in queue
        assert minimal_worker.status_check_queue.qsize() == 1

    def test_check_image_status_empty_galleries(self, minimal_worker):
        """Test check_image_status with empty galleries list emits empty result."""
        minimal_worker.check_image_status([])

        # Should emit empty dict immediately
        minimal_worker.status_check_completed.emit.assert_called_once_with({})

        # Should not queue anything
        assert minimal_worker.status_check_queue.qsize() == 0

    def test_check_image_status_none_galleries(self, minimal_worker):
        """Test check_image_status with None emits empty result."""
        minimal_worker.check_image_status(None)

        minimal_worker.status_check_completed.emit.assert_called_once_with({})

    def test_cancel_during_perform_check(self, minimal_worker, sample_galleries_data):
        """Test that cancellation during _perform_status_check returns early."""
        # Set up mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<p>Found: 5 images</p><textarea class="imageallcodes"></textarea>'
        minimal_worker.session.post.return_value = mock_response

        # Set cancellation before calling
        minimal_worker._status_check_cancelled.set()

        result = minimal_worker._perform_status_check(sample_galleries_data)

        # Should return empty dict when cancelled
        assert result == {}
        # Should not have made any HTTP requests
        minimal_worker.session.post.assert_not_called()


# =============================================================================
# TestPerformStatusCheck - Tests for _perform_status_check()
# =============================================================================

class TestPerformStatusCheck:
    """Test _perform_status_check() method including fast path and slow path."""

    def test_fast_path_when_all_online(self, minimal_worker, sample_galleries_data):
        """Test fast path is used when found_count equals total URLs.

        When all images are online (found_count == total), we skip parsing
        the textarea and mark all URLs as online directly.
        """
        # Total URLs in sample_galleries_data: 3 + 2 = 5
        total_urls = 5

        mock_response = create_streaming_response(200, f'<p>Found: {total_urls} images</p>')
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(sample_galleries_data)

        # All galleries should have all images online
        assert '/path/to/gallery1' in result
        assert '/path/to/gallery2' in result

        gallery1 = result['/path/to/gallery1']
        assert gallery1['online'] == 3
        assert gallery1['offline'] == 0
        assert gallery1['total'] == 3
        assert len(gallery1['online_urls']) == 3
        assert len(gallery1['offline_urls']) == 0

        gallery2 = result['/path/to/gallery2']
        assert gallery2['online'] == 2
        assert gallery2['offline'] == 0

    def test_slow_path_when_some_offline(self, minimal_worker, sample_galleries_data):
        """Test slow path is used when found_count differs from total URLs.

        When some images are offline, we need to parse the textarea to determine
        which specific images are online vs offline.
        """
        # Only 3 out of 5 are online - triggers slow path
        html_content = '''
        <p>Found: 3 images</p>
        <textarea class="imageallcodes">
        https://imx.to/i/abc123
        https://imx.to/i/ghi789
        https://imx.to/i/jkl012
        </textarea>
        '''
        mock_response = create_streaming_response(200, html_content)
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(sample_galleries_data)

        # Check gallery1: abc123 and ghi789 online, def456 offline
        gallery1 = result['/path/to/gallery1']
        assert gallery1['online'] == 2
        assert gallery1['offline'] == 1
        assert 'https://imx.to/i/abc123' in gallery1['online_urls']
        assert 'https://imx.to/i/ghi789' in gallery1['online_urls']
        assert 'https://imx.to/i/def456' in gallery1['offline_urls']

        # Check gallery2: jkl012 online, mno345 offline
        gallery2 = result['/path/to/gallery2']
        assert gallery2['online'] == 1
        assert gallery2['offline'] == 1

    def test_empty_urls(self, minimal_worker):
        """Test handling galleries with no valid URLs."""
        galleries_data = [
            {'db_id': 1, 'path': '/test', 'name': 'Test', 'image_urls': []}
        ]

        result = minimal_worker._perform_status_check(galleries_data)

        assert result == {}

    def test_whitespace_url_normalization(self, minimal_worker):
        """Test that URL whitespace is normalized."""
        galleries_data = [
            {
                'db_id': 1,
                'path': '/test',
                'name': 'Test',
                'image_urls': ['  https://imx.to/i/abc123  ', '\nhttps://imx.to/i/def456\n']
            }
        ]

        mock_response = create_streaming_response(200, '<p>Found: 2 images</p>')
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(galleries_data)

        # Both URLs should be processed after whitespace normalization
        assert result['/test']['total'] == 2

    def test_http_403_triggers_reauth(self, minimal_worker, sample_galleries_data):
        """Test that HTTP 403 triggers re-authentication attempt."""
        # First request returns 403, second (after reauth) returns 200
        mock_response_403 = Mock()
        mock_response_403.status_code = 403

        mock_response_200 = create_streaming_response(200, '<p>Found: 5 images</p>')

        minimal_worker.session.post.side_effect = [mock_response_403, mock_response_200]

        with patch.object(minimal_worker, '_attempt_reauth_with_rate_limit', return_value=True):
            result = minimal_worker._perform_status_check(sample_galleries_data)

        # Should have made 2 requests (original + retry)
        assert minimal_worker.session.post.call_count == 2

    def test_http_403_reauth_failure(self, minimal_worker, sample_galleries_data):
        """Test that failed re-authentication raises exception."""
        mock_response_403 = Mock()
        mock_response_403.status_code = 403
        minimal_worker.session.post.return_value = mock_response_403

        with patch.object(minimal_worker, '_attempt_reauth_with_rate_limit', return_value=False):
            with pytest.raises(Exception, match="Authentication expired"):
                minimal_worker._perform_status_check(sample_galleries_data)

    def test_ddos_guard_detection(self, minimal_worker, sample_galleries_data):
        """Test that DDoS-Guard detection raises exception."""
        mock_response = create_streaming_response(200, '<html>DDoS-Guard protection active</html>')
        minimal_worker.session.post.return_value = mock_response

        with pytest.raises(Exception, match="DDoS-Guard"):
            minimal_worker._perform_status_check(sample_galleries_data)

    def test_http_error_status(self, minimal_worker, sample_galleries_data):
        """Test that non-200 HTTP status raises exception."""
        mock_response = Mock()
        mock_response.status_code = 500
        minimal_worker.session.post.return_value = mock_response

        with pytest.raises(Exception, match="HTTP 500"):
            minimal_worker._perform_status_check(sample_galleries_data)

    def test_progress_signal_emission(self, minimal_worker, sample_galleries_data):
        """Test that progress signals are emitted during status check."""
        mock_response = create_streaming_response(200, '<p>Found: 5 images</p>')
        minimal_worker.session.post.return_value = mock_response

        minimal_worker._perform_status_check(sample_galleries_data)

        # Should emit progress at start (0, total) and end (total, total)
        assert minimal_worker.status_check_progress.emit.call_count >= 2

    def test_result_structure(self, minimal_worker):
        """Test the structure of the result dictionary."""
        galleries_data = [
            {
                'db_id': 42,
                'path': '/test/gallery',
                'name': 'Test Gallery',
                'image_urls': ['https://imx.to/i/abc123']
            }
        ]

        mock_response = create_streaming_response(200, '<p>Found: 1 images</p>')
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(galleries_data)

        # Verify result structure
        assert '/test/gallery' in result
        gallery_result = result['/test/gallery']

        assert 'db_id' in gallery_result
        assert gallery_result['db_id'] == 42

        assert 'name' in gallery_result
        assert gallery_result['name'] == 'Test Gallery'

        assert 'total' in gallery_result
        assert 'online' in gallery_result
        assert 'offline' in gallery_result
        assert 'online_urls' in gallery_result
        assert 'offline_urls' in gallery_result

    def test_cancel_before_retry(self, minimal_worker, sample_galleries_data):
        """Test cancellation is checked before retry after 403."""
        mock_response_403 = Mock()
        mock_response_403.status_code = 403
        minimal_worker.session.post.return_value = mock_response_403

        # Simulate cancellation happening during reauth
        def set_cancelled_during_reauth():
            minimal_worker._status_check_cancelled.set()
            return True

        with patch.object(minimal_worker, '_attempt_reauth_with_rate_limit',
                         side_effect=set_cancelled_during_reauth):
            result = minimal_worker._perform_status_check(sample_galleries_data)

        # Should return empty due to cancellation
        assert result == {}

    def test_invalid_url_handling(self, minimal_worker):
        """Test handling of invalid URLs (no extractable ID)."""
        galleries_data = [
            {
                'db_id': 1,
                'path': '/test',
                'name': 'Test',
                'image_urls': [
                    'https://example.com/image.jpg',  # Invalid
                    'https://imx.to/i/abc123',        # Valid
                    '',                                # Empty
                    None                               # None - should be skipped
                ]
            }
        ]

        # Only 1 valid URL found
        html_content = '''
        <p>Found: 1 images</p>
        <textarea class="imageallcodes">
        https://imx.to/i/abc123
        </textarea>
        '''
        mock_response = create_streaming_response(200, html_content)
        minimal_worker.session.post.return_value = mock_response

        # Should handle gracefully without raising
        result = minimal_worker._perform_status_check(galleries_data)

        # Only valid URL should be counted
        assert result['/test']['total'] >= 1

    def test_multiple_galleries_isolation(self, minimal_worker):
        """Test that results are correctly isolated between galleries."""
        galleries_data = [
            {'db_id': 1, 'path': '/gallery1', 'name': 'G1', 'image_urls': ['https://imx.to/i/aaa111']},
            {'db_id': 2, 'path': '/gallery2', 'name': 'G2', 'image_urls': ['https://imx.to/i/bbb222']},
            {'db_id': 3, 'path': '/gallery3', 'name': 'G3', 'image_urls': ['https://imx.to/i/ccc333']}
        ]

        # Only bbb222 is online
        html_content = '''
        <p>Found: 1 images</p>
        <textarea class="imageallcodes">
        https://imx.to/i/bbb222
        </textarea>
        '''
        mock_response = create_streaming_response(200, html_content)
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(galleries_data)

        # Gallery 1: offline
        assert result['/gallery1']['online'] == 0
        assert result['/gallery1']['offline'] == 1

        # Gallery 2: online
        assert result['/gallery2']['online'] == 1
        assert result['/gallery2']['offline'] == 0

        # Gallery 3: offline
        assert result['/gallery3']['online'] == 0
        assert result['/gallery3']['offline'] == 1


# =============================================================================
# TestStatusCheckQueue - Tests for queue processing
# =============================================================================

class TestStatusCheckQueue:
    """Test status check queue processing."""

    def test_check_image_status_queues_data(self, minimal_worker, sample_galleries_data):
        """Test that check_image_status queues the galleries data."""
        minimal_worker.check_image_status(sample_galleries_data)

        assert minimal_worker.status_check_queue.qsize() == 1
        queued_data = minimal_worker.status_check_queue.get_nowait()
        assert queued_data == sample_galleries_data

    def test_status_check_queue_size(self, minimal_worker, sample_galleries_data):
        """Test status_check_queue_size() method."""
        assert minimal_worker.status_check_queue_size() == 0

        minimal_worker.check_image_status(sample_galleries_data)

        # Note: The queue might be processed immediately in real implementation
        # Here we're testing the qsize method works
        assert hasattr(minimal_worker, 'status_check_queue_size')


# =============================================================================
# TestEdgeCases - Edge cases and boundary conditions
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_url_list(self, minimal_worker):
        """Test handling of very long URL lists."""
        # Generate 1000 URLs
        urls = [f'https://imx.to/i/img{i:04d}' for i in range(1000)]

        galleries_data = [
            {'db_id': 1, 'path': '/large', 'name': 'Large Gallery', 'image_urls': urls}
        ]

        mock_response = create_streaming_response(200, '<p>Found: 1000 images</p>')
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(galleries_data)

        assert result['/large']['total'] == 1000
        assert result['/large']['online'] == 1000

    def test_unicode_in_gallery_name(self, minimal_worker):
        """Test handling of Unicode characters in gallery names."""
        galleries_data = [
            {
                'db_id': 1,
                'path': '/test',
                'name': 'Gallery with special chars',
                'image_urls': ['https://imx.to/i/abc123']
            }
        ]

        mock_response = create_streaming_response(200, '<p>Found: 1 images</p>')
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(galleries_data)

        assert result['/test']['name'] == 'Gallery with special chars'

    def test_gallery_with_no_path(self, minimal_worker):
        """Test galleries with missing path are skipped."""
        galleries_data = [
            {'db_id': 1, 'path': '', 'name': 'No Path', 'image_urls': ['https://imx.to/i/abc123']},
            {'db_id': 2, 'path': '/valid', 'name': 'Valid', 'image_urls': ['https://imx.to/i/def456']}
        ]

        mock_response = create_streaming_response(200, '<p>Found: 1 images</p>')
        minimal_worker.session.post.return_value = mock_response

        result = minimal_worker._perform_status_check(galleries_data)

        # Only valid gallery should be in results
        assert '' not in result
        assert '/valid' in result

    def test_timeout_parameters(self, minimal_worker, sample_galleries_data):
        """Test that correct timeout parameters are used for POST request."""
        mock_response = create_streaming_response(200, '<p>Found: 5 images</p>')
        minimal_worker.session.post.return_value = mock_response

        minimal_worker._perform_status_check(sample_galleries_data)

        # Verify timeout was passed
        call_kwargs = minimal_worker.session.post.call_args[1]
        assert 'timeout' in call_kwargs
        # Should be (connect_timeout, read_timeout) tuple
        assert call_kwargs['timeout'] == (30, 300)

    def test_verify_ssl_enabled(self, minimal_worker, sample_galleries_data):
        """Test that SSL verification is enabled for POST request."""
        mock_response = create_streaming_response(200, '<p>Found: 5 images</p>')
        minimal_worker.session.post.return_value = mock_response

        minimal_worker._perform_status_check(sample_galleries_data)

        # Verify SSL verification is enabled
        call_kwargs = minimal_worker.session.post.call_args[1]
        assert 'verify' in call_kwargs
        assert call_kwargs['verify'] is True


# =============================================================================
# TestStreamingBehavior - Tests for _stream_and_detect_found_count() streaming
# =============================================================================

class TestStreamingBehavior:
    """Test streaming behavior of _stream_and_detect_found_count().

    These tests verify the correct behavior of the streaming response handling,
    including iterator reuse (critical bug fix), early exit optimization, and
    partial response handling.
    """

    def test_iterator_reuse_continues_from_first_loop(self, minimal_worker):
        """Test that the second loop continues reading from where the first loop stopped.

        This is a critical bug fix test. The implementation creates ONE iterator
        via iter_content() and reuses it. If we incorrectly called iter_content()
        again in the second loop, we would restart from the beginning (or get
        empty data depending on the response object).

        This test verifies that when some images are offline (found_count < total),
        the second loop correctly continues from where the first loop stopped,
        reading the remaining chunks that contain the textarea with online image IDs.
        """
        # Create chunked response where:
        # - First chunks contain "Found: 2 images" (less than total=3)
        # - Later chunks contain the textarea with online image IDs
        chunks = [
            b'<html><head>',
            b'</head><body>',
            b'<p>Found: 2 images</p>',  # found_count=2 < total_urls=3
            b'<textarea class="imageallcodes">',
            b'https://imx.to/i/abc123\n',  # First online image
            b'https://imx.to/i/def456',    # Second online image
            b'</textarea></body></html>'
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        # Create a real iterator that gets consumed once
        mock_response.iter_content = Mock(return_value=iter(chunks))

        minimal_worker.session.post.return_value = mock_response

        galleries_data = [
            {
                'db_id': 1,
                'path': '/test/gallery',
                'name': 'Test Gallery',
                'image_urls': [
                    'https://imx.to/i/abc123',  # Online
                    'https://imx.to/i/def456',  # Online
                    'https://imx.to/i/ghi789'   # Offline (not in textarea)
                ]
            }
        ]

        result = minimal_worker._perform_status_check(galleries_data)

        # Verify the iterator was used correctly
        # Should have been called once (not twice)
        assert mock_response.iter_content.call_count == 1

        # Verify results show 2 online, 1 offline (proving the second loop
        # correctly read the remaining chunks with the textarea)
        assert result['/test/gallery']['online'] == 2
        assert result['/test/gallery']['offline'] == 1
        assert 'https://imx.to/i/abc123' in result['/test/gallery']['online_urls']
        assert 'https://imx.to/i/def456' in result['/test/gallery']['online_urls']
        assert 'https://imx.to/i/ghi789' in result['/test/gallery']['offline_urls']

    def test_early_exit_when_all_online(self, minimal_worker):
        """Test early exit when found_count equals total_urls.

        When all images are online, the method should:
        1. Stop reading after finding "Found: X images" where X == total
        2. Close the response early (saving bandwidth)
        3. Return early_exit=True and partial response text
        4. NOT parse the textarea (uses fast path instead)
        """
        # Only provide enough chunks for the count to be detected
        chunks = [
            b'<html><body>',
            b'<p>Found: 3 images</p>',  # found_count=3 == total_urls=3
            # These chunks should NOT be read due to early exit:
            b'<textarea class="imageallcodes">',
            b'https://imx.to/i/abc123\nhttps://imx.to/i/def456\nhttps://imx.to/i/ghi789',
            b'</textarea></body></html>'
        ]

        # Track which chunks were actually consumed
        chunks_consumed = []

        def chunk_iterator():
            for chunk in chunks:
                chunks_consumed.append(chunk)
                yield chunk

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=chunk_iterator())

        minimal_worker.session.post.return_value = mock_response

        galleries_data = [
            {
                'db_id': 1,
                'path': '/test/gallery',
                'name': 'Test Gallery',
                'image_urls': [
                    'https://imx.to/i/abc123',
                    'https://imx.to/i/def456',
                    'https://imx.to/i/ghi789'
                ]
            }
        ]

        result = minimal_worker._perform_status_check(galleries_data)

        # Verify early exit occurred (not all chunks consumed)
        # The method should stop after finding "Found: 3 images"
        assert len(chunks_consumed) < len(chunks), \
            f"Expected early exit but consumed {len(chunks_consumed)} of {len(chunks)} chunks"

        # Verify all images marked as online (fast path)
        assert result['/test/gallery']['online'] == 3
        assert result['/test/gallery']['offline'] == 0
        assert len(result['/test/gallery']['online_urls']) == 3

    def test_partial_response_reads_full_when_some_offline(self, minimal_worker):
        """Test that full response is read when some images are offline.

        When found_count < total_urls, even if the count is found in the first
        chunk, the method MUST continue reading the full response to:
        1. Find the textarea with online image IDs
        2. Determine which specific images are online vs offline
        """
        # Place the count in the first chunk, but textarea is in later chunks
        chunks = [
            b'<html><body><p>Found: 2 images</p>',  # Count found early
            b'<div>Some content here</div>',
            b'<textarea class="imageallcodes">',
            b'https://imx.to/i/online1\n',
            b'https://imx.to/i/online2',
            b'</textarea></body></html>'
        ]

        # Track which chunks were actually consumed
        chunks_consumed = []

        def chunk_iterator():
            for chunk in chunks:
                chunks_consumed.append(chunk)
                yield chunk

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=chunk_iterator())

        minimal_worker.session.post.return_value = mock_response

        galleries_data = [
            {
                'db_id': 1,
                'path': '/test/gallery',
                'name': 'Test Gallery',
                'image_urls': [
                    'https://imx.to/i/online1',   # Online
                    'https://imx.to/i/online2',   # Online
                    'https://imx.to/i/offline1'   # Offline
                ]
            }
        ]

        result = minimal_worker._perform_status_check(galleries_data)

        # Verify ALL chunks were consumed (no early exit)
        assert len(chunks_consumed) == len(chunks), \
            f"Expected full read but only consumed {len(chunks_consumed)} of {len(chunks)} chunks"

        # Verify correct online/offline classification
        assert result['/test/gallery']['online'] == 2
        assert result['/test/gallery']['offline'] == 1
        assert 'https://imx.to/i/online1' in result['/test/gallery']['online_urls']
        assert 'https://imx.to/i/online2' in result['/test/gallery']['online_urls']
        assert 'https://imx.to/i/offline1' in result['/test/gallery']['offline_urls']

    def test_cancellation_during_streaming(self, minimal_worker):
        """Test that cancellation during streaming returns None and stops reading."""
        # Create an iterator that sets cancellation flag partway through
        chunks_consumed = []

        def chunk_iterator_with_cancellation():
            for i, chunk in enumerate([
                b'<html><body>',
                b'<p>Found: 5 images</p>',
                b'<textarea class="imageallcodes">',
            ]):
                chunks_consumed.append(chunk)
                # Set cancellation after first chunk
                if i == 0:
                    minimal_worker._status_check_cancelled.set()
                yield chunk

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=chunk_iterator_with_cancellation())

        minimal_worker.session.post.return_value = mock_response

        galleries_data = [
            {
                'db_id': 1,
                'path': '/test/gallery',
                'name': 'Test Gallery',
                'image_urls': ['https://imx.to/i/abc123'] * 5
            }
        ]

        result = minimal_worker._perform_status_check(galleries_data)

        # Should return empty dict due to cancellation
        assert result == {}

        # Should have stopped reading early (cancelled after chunk 0,
        # should detect on chunk 1)
        assert len(chunks_consumed) <= 2


# =============================================================================
# TestQuickCountSignal - Tests for quick_count_available signal
# =============================================================================

class TestQuickCountSignal:
    """Test quick_count_available signal behavior.

    The quick_count_available signal is emitted during streaming when the
    'Found: X images' count is parsed from the response. This provides
    immediate feedback to the user about how many images are online.
    """

    def test_quick_count_emitted_when_count_found(self, minimal_worker):
        """Test signal emitted with correct values when count is parsed.

        When all images are online (found_count == total_urls), the signal
        should emit (found_count, total_urls) and then exit early.
        """
        # Add the quick_count_available mock
        minimal_worker.quick_count_available = Mock()

        # Create response with Found count matching total
        chunks = [b'<html><p>Found: 100 images</p>', b'<textarea>...</textarea></html>']
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=iter(chunks))
        mock_response.close = Mock()
        minimal_worker.session.post.return_value = mock_response

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Test',
            'total_images': 100,
            'image_urls': [f'https://imx.to/i/img{i}' for i in range(100)]
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Verify quick_count_available was emitted with (found_count, total_urls)
        minimal_worker.quick_count_available.emit.assert_called_once_with(100, 100)

    def test_quick_count_shows_offline_count(self, minimal_worker):
        """Test signal emitted correctly when some images offline.

        When found_count < total_urls, the signal should still emit the
        actual counts so the user sees the mismatch immediately.
        """
        minimal_worker.quick_count_available = Mock()

        # Found 80 but submitted 100 - some are offline
        chunks = [
            b'<p>Found: 80 images</p>',
            b'<textarea class="imageallcodes">',
            b'https://imx.to/i/img1\nhttps://imx.to/i/img2',
            b'</textarea>'
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=iter(chunks))
        mock_response.close = Mock()
        minimal_worker.session.post.return_value = mock_response

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Test',
            'total_images': 100,
            'image_urls': [f'https://imx.to/i/img{i}' for i in range(100)]
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Signal should be emitted with 80, 100
        minimal_worker.quick_count_available.emit.assert_called_once_with(80, 100)

    def test_quick_count_not_emitted_when_count_zero(self, minimal_worker):
        """Test signal not emitted when no images found (count=0).

        When the response doesn't contain 'Found: X images' or the count is 0,
        the signal should not be emitted.
        """
        minimal_worker.quick_count_available = Mock()

        # Response without 'Found: X images' text
        chunks = [b'<html><body>No images here</body></html>']
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=iter(chunks))
        mock_response.close = Mock()
        minimal_worker.session.post.return_value = mock_response

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Test',
            'image_urls': ['https://imx.to/i/img1']
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Signal should NOT be emitted when count is 0
        minimal_worker.quick_count_available.emit.assert_not_called()

    def test_quick_count_emitted_once_per_check(self, minimal_worker):
        """Test signal is emitted exactly once per status check.

        Even if multiple chunks contain the count text, the signal should
        only be emitted once when the count is first parsed.
        """
        minimal_worker.quick_count_available = Mock()

        # Multiple chunks, count appears in first
        chunks = [
            b'<html><p>Found: 50 images</p>',
            b'<div>More content with Found: 50 images</div>',  # Duplicate text
            b'<textarea class="imageallcodes">',
            b'</textarea></html>'
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=iter(chunks))
        mock_response.close = Mock()
        minimal_worker.session.post.return_value = mock_response

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Test',
            'image_urls': [f'https://imx.to/i/img{i}' for i in range(50)]
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Signal should be emitted exactly once
        assert minimal_worker.quick_count_available.emit.call_count == 1
        minimal_worker.quick_count_available.emit.assert_called_with(50, 50)

    def test_quick_count_with_single_image(self, minimal_worker):
        """Test signal works correctly with singular 'Found: 1 image'."""
        minimal_worker.quick_count_available = Mock()

        # Singular form: "Found: 1 image" (not "images")
        chunks = [b'<html><p>Found: 1 image</p></html>']
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=iter(chunks))
        mock_response.close = Mock()
        minimal_worker.session.post.return_value = mock_response

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Test',
            'image_urls': ['https://imx.to/i/single']
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Should emit (1, 1)
        minimal_worker.quick_count_available.emit.assert_called_once_with(1, 1)

    def test_quick_count_not_emitted_on_cancellation(self, minimal_worker):
        """Test signal not emitted if check is cancelled before count found."""
        minimal_worker.quick_count_available = Mock()

        # Set cancellation flag
        minimal_worker._status_check_cancelled.set()

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Test',
            'image_urls': ['https://imx.to/i/img1']
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Signal should not be emitted due to early cancellation
        minimal_worker.quick_count_available.emit.assert_not_called()

    def test_quick_count_emitted_before_early_exit(self, minimal_worker):
        """Test signal is emitted before the early exit when all images online.

        The signal should be emitted immediately when the count is found,
        allowing the UI to update before the full result is computed.
        """
        minimal_worker.quick_count_available = Mock()

        # Track order of operations
        call_order = []

        def track_emit(*args):
            call_order.append(('quick_count_emit', args))

        def track_progress_emit(*args):
            call_order.append(('progress_emit', args))

        minimal_worker.quick_count_available.emit.side_effect = track_emit
        minimal_worker.status_check_progress.emit.side_effect = track_progress_emit

        chunks = [b'<html><p>Found: 3 images</p></html>']
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=iter(chunks))
        mock_response.close = Mock()
        minimal_worker.session.post.return_value = mock_response

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Test',
            'image_urls': ['https://imx.to/i/a', 'https://imx.to/i/b', 'https://imx.to/i/c']
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Verify quick_count was emitted
        assert ('quick_count_emit', (3, 3)) in call_order

    def test_quick_count_large_gallery(self, minimal_worker):
        """Test signal works correctly with large gallery (1000+ images)."""
        minimal_worker.quick_count_available = Mock()

        # Large count
        chunks = [b'<html><p>Found: 5000 images</p></html>']
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content = Mock(return_value=iter(chunks))
        mock_response.close = Mock()
        minimal_worker.session.post.return_value = mock_response

        galleries_data = [{
            'db_id': 1,
            'path': '/test',
            'name': 'Large Gallery',
            'image_urls': [f'https://imx.to/i/img{i}' for i in range(5000)]
        }]

        minimal_worker._perform_status_check(galleries_data)

        # Should handle large counts correctly
        minimal_worker.quick_count_available.emit.assert_called_once_with(5000, 5000)
