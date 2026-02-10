# tests/unit/processing/test_cover_upload.py
"""Tests for cover photo upload through RenameWorker."""
import pytest
from unittest.mock import patch, MagicMock, mock_open, ANY


@pytest.fixture
def worker():
    """Create a RenameWorker with mocked dependencies."""
    with patch('threading.Thread'), \
         patch('requests.Session') as mock_session_class, \
         patch('bbdrop.get_credential', return_value=None):
        from src.processing.rename_worker import RenameWorker
        w = RenameWorker()
        # Replace the session with a fresh mock for test control
        w.session = MagicMock()
        w.web_url = "https://imx.to"
        w.login_successful = True
        w.login_complete = MagicMock()
        w.login_complete.is_set.return_value = True
        return w


class TestCoverUpload:
    """RenameWorker.upload_cover posts to the cover endpoint."""

    def test_upload_cover_success(self, worker):
        # Mock the POST response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '''
            <textarea class="imageallcodes">
            [url=https://imx.to/i/abc123][img]https://t.imx.to/t/abc123.jpg[/img][/url]
            </textarea>
        '''
        worker.session.post.return_value = mock_response

        with patch('builtins.open', mock_open(read_data=b'\xff\xd8\xff')):
            result = worker.upload_cover(
                image_path="/tmp/cover.jpg",
                gallery_id="gal123",
                thumbnail_format=2,
            )

        assert result is not None
        assert result["status"] == "success"
        assert result["image_url"] == "https://imx.to/i/abc123"
        assert result["thumb_url"] == "https://t.imx.to/t/abc123.jpg"
        worker.session.post.assert_called_once()
        call_args = worker.session.post.call_args
        assert "mode=cover" in call_args[0][0] or "cover" in str(call_args)

    def test_upload_cover_not_authenticated(self, worker):
        worker.login_successful = False

        result = worker.upload_cover(
            image_path="/tmp/cover.jpg",
            gallery_id="gal123",
        )

        assert result is None

    def test_upload_cover_failure_returns_none(self, worker):
        # Mock server error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        worker.session.post.return_value = mock_response

        with patch('builtins.open', mock_open(read_data=b'\xff\xd8\xff')):
            result = worker.upload_cover(
                image_path="/tmp/cover.jpg",
                gallery_id="gal123",
            )

        assert result is None

    def test_upload_cover_no_bbcode_in_response(self, worker):
        """Response without textarea returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><body>No codes here</body></html>'
        worker.session.post.return_value = mock_response

        with patch('builtins.open', mock_open(read_data=b'\xff\xd8\xff')):
            result = worker.upload_cover(
                image_path="/tmp/cover.jpg",
                gallery_id="gal123",
            )

        assert result is None

    def test_upload_cover_exception_returns_none(self, worker):
        """Network exception returns None."""
        worker.session.post.side_effect = ConnectionError("Connection refused")

        with patch('builtins.open', mock_open(read_data=b'\xff\xd8\xff')):
            result = worker.upload_cover(
                image_path="/tmp/cover.jpg",
                gallery_id="gal123",
            )

        assert result is None

    def test_upload_cover_sends_gallery_id(self, worker):
        """Gallery ID is included in form data when provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '''
            <textarea class="imageallcodes">
            [url=https://imx.to/i/xyz789][img]https://t.imx.to/t/xyz789.jpg[/img][/url]
            </textarea>
        '''
        worker.session.post.return_value = mock_response

        with patch('builtins.open', mock_open(read_data=b'\xff\xd8\xff')):
            worker.upload_cover(
                image_path="/tmp/cover.jpg",
                gallery_id="mygallery",
            )

        call_kwargs = worker.session.post.call_args
        # The data dict should contain set_gallery
        data = call_kwargs[1].get('data') or call_kwargs.kwargs.get('data', {})
        assert data.get('set_gallery') == 'mygallery'

    def test_upload_cover_posts_to_cover_endpoint(self, worker):
        """URL must contain ?mode=cover."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '''
            <textarea class="imageallcodes">
            [url=https://imx.to/i/abc][img]https://t.imx.to/t/abc.jpg[/img][/url]
            </textarea>
        '''
        worker.session.post.return_value = mock_response

        with patch('builtins.open', mock_open(read_data=b'\xff\xd8\xff')):
            worker.upload_cover(
                image_path="/tmp/cover.jpg",
                gallery_id="gal1",
            )

        url_arg = worker.session.post.call_args[0][0]
        assert url_arg == "https://imx.to/?mode=cover"


class TestParseCoverResponse:
    """RenameWorker._parse_cover_response extracts BBCode, image URL, thumb URL."""

    def test_parse_valid_response(self, worker):
        html = '''
        <textarea class="imageallcodes">
        [url=https://imx.to/i/abc123][img]https://t.imx.to/t/abc123.jpg[/img][/url]
        </textarea>
        '''
        bbcode, image_url, thumb_url = worker._parse_cover_response(html)

        assert image_url == "https://imx.to/i/abc123"
        assert thumb_url == "https://t.imx.to/t/abc123.jpg"
        assert "[url=" in bbcode

    def test_parse_empty_response(self, worker):
        bbcode, image_url, thumb_url = worker._parse_cover_response("")

        assert bbcode == ""
        assert image_url == ""
        assert thumb_url == ""

    def test_parse_no_textarea(self, worker):
        html = '<html><body>No textarea here</body></html>'
        bbcode, image_url, thumb_url = worker._parse_cover_response(html)

        assert bbcode == ""
        assert image_url == ""
        assert thumb_url == ""

    def test_parse_multiple_bbcode_formats(self, worker):
        """Handles different BBCode URL structures."""
        html = '''
        <textarea class="imageallcodes">
        [url=https://imx.to/i/x1y2z3][img]https://t.imx.to/t/x1y2z3.jpg[/img][/url]
        </textarea>
        '''
        bbcode, image_url, thumb_url = worker._parse_cover_response(html)

        assert image_url == "https://imx.to/i/x1y2z3"
        assert thumb_url == "https://t.imx.to/t/x1y2z3.jpg"
