"""Tests for ThumbnailChecker — batch thumbnail liveness via HEAD + ETag."""

import pytest
from unittest.mock import patch, Mock, call

from src.network.thumbnail_checker import ThumbnailChecker


@pytest.fixture
def checker():
    return ThumbnailChecker(max_workers=2)


class TestThumbnailCheckerBasic:
    """Test basic check_gallery functionality."""

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_all_online(self, mock_head, checker):
        """All thumbnails online should return online status."""
        mock_head.return_value = {'url': 'u', 'status': 'online', 'etag': '"abc"'}
        urls = [f'https://host.com/thumb{i}.jpg' for i in range(5)]

        result = checker.check_gallery(urls)
        assert result['status'] == 'online'
        assert result['online'] == 5
        assert result['total'] == 5

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_all_offline(self, mock_head, checker):
        """All thumbnails offline should return offline status."""
        mock_head.return_value = {'url': 'u', 'status': 'offline', 'etag': '"65c43e4c-23a8"'}
        urls = [f'https://host.com/thumb{i}.jpg' for i in range(5)]

        result = checker.check_gallery(urls)
        assert result['status'] == 'offline'
        assert result['online'] == 0

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_partial(self, mock_head, checker):
        """Mix of online/offline should return partial."""
        def side_effect(url, **kwargs):
            if 'thumb0' in url:
                return {'url': url, 'status': 'offline', 'etag': '"65c43e4c-23a8"'}
            return {'url': url, 'status': 'online', 'etag': '"live"'}

        mock_head.side_effect = side_effect
        urls = [f'https://host.com/thumb{i}.jpg' for i in range(3)]

        result = checker.check_gallery(urls)
        assert result['status'] == 'partial'
        assert result['online'] == 2
        assert result['offline'] == 1

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_empty_urls_returns_unknown(self, mock_head, checker):
        """Empty URL list should return unknown status."""
        result = checker.check_gallery([])
        assert result['status'] == 'unknown'
        assert result['total'] == 0
        mock_head.assert_not_called()


class TestThumbnailCheckerEarlyExit:
    """Test early-exit behavior when first N thumbs are all offline."""

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_early_exit_skips_remaining(self, mock_head, checker):
        """If first early_exit_threshold thumbs are all offline, skip the rest."""
        mock_head.return_value = {'url': 'u', 'status': 'offline', 'etag': '"dead"'}
        urls = [f'https://host.com/thumb{i}.jpg' for i in range(100)]

        result = checker.check_gallery(urls, early_exit_threshold=5)
        assert result['status'] == 'offline'
        # Should have checked at most early_exit_threshold URLs, not all 100
        assert mock_head.call_count <= 10  # some slack for concurrency

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_no_early_exit_if_some_online(self, mock_head):
        """If any thumb in first batch is online, continue checking all."""
        call_count = 0
        def side_effect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                return {'url': url, 'status': 'online', 'etag': '"live"'}
            return {'url': url, 'status': 'offline', 'etag': '"dead"'}

        mock_head.side_effect = side_effect
        checker = ThumbnailChecker(max_workers=1)  # sequential for determinism
        urls = [f'https://host.com/thumb{i}.jpg' for i in range(10)]

        result = checker.check_gallery(urls, early_exit_threshold=5)
        # Should NOT early-exit because thumb2 was online
        assert result['total'] == 10


class TestThumbnailCheckerCancellation:
    """Test cancellation via threading.Event."""

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_cancel_stops_checking(self, mock_head):
        """Setting cancel_event should stop processing."""
        import threading
        cancel = threading.Event()
        cancel.set()  # Pre-cancel

        mock_head.return_value = {'url': 'u', 'status': 'online', 'etag': '"abc"'}
        checker = ThumbnailChecker(max_workers=1)
        urls = [f'https://host.com/thumb{i}.jpg' for i in range(50)]

        result = checker.check_gallery(urls, cancel_event=cancel)
        # Should have been cancelled immediately
        assert mock_head.call_count < 50


class TestThumbnailCheckerProgress:
    """Test progress callback invocation."""

    @patch('src.network.thumbnail_checker.check_thumbnail_head')
    def test_progress_callback_called(self, mock_head):
        """Progress callback should be called with (checked, total)."""
        mock_head.return_value = {'url': 'u', 'status': 'online', 'etag': '"abc"'}
        checker = ThumbnailChecker(max_workers=1)
        progress_calls = []

        def on_progress(checked, total):
            progress_calls.append((checked, total))

        urls = [f'https://host.com/thumb{i}.jpg' for i in range(5)]
        checker.check_gallery(urls, progress_callback=on_progress)

        assert len(progress_calls) > 0
        assert progress_calls[-1] == (5, 5)
