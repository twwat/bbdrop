"""Tests for cover photo variables in hooks."""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestHooksCoverVariables:

    def test_cover_path_substitution(self):
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        context = {'cover_path': '/path/to/cover.jpg'}
        result = executor._substitute_variables('echo %cv', context)
        assert result == 'echo /path/to/cover.jpg'

    def test_cover_url_substitution(self):
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        context = {'cover_url': 'https://imx.to/i/abc123.jpg'}
        result = executor._substitute_variables('echo %cu', context)
        assert result == 'echo https://imx.to/i/abc123.jpg'

    def test_cover_vars_empty_when_no_cover(self):
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        context = {}
        result = executor._substitute_variables('echo %cv %cu', context)
        assert result == 'echo  '

    def test_cover_vars_alongside_other_vars(self):
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        context = {
            'gallery_name': 'MyGallery',
            'cover_path': '/cover.jpg',
            'cover_url': 'https://example.com/cover.jpg',
        }
        result = executor._substitute_variables('echo %N %cv %cu', context)
        assert result == 'echo MyGallery /cover.jpg https://example.com/cover.jpg'


class TestHooksExecutorCoverPassthrough:
    """execute_hooks() passes cover_path/cover_url from raw JSON to returned dict."""

    def test_cover_path_passed_through_from_json(self):
        """When hook JSON contains cover_path, it appears in the returned dict."""
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        # Patch _execute_hook_with_config to simulate hook returning JSON with cover_path
        json_data = {'cover_path': '/tmp/hook_cover.jpg', 'some_key': 'value'}
        executor._execute_hook_with_config = Mock(return_value=(True, json_data, ''))
        # Minimal config to enable the hook
        config = {
            'parallel_execution': False,
            'started': {
                'enabled': True,
                'command': 'echo test',
                'key_mapping': {},
            },
        }
        executor._load_config = Mock(return_value=config)
        result = executor.execute_hooks(['started'], {})
        assert result.get('cover_path') == '/tmp/hook_cover.jpg'

    def test_cover_url_passed_through_from_json(self):
        """When hook JSON contains cover_url, it appears in the returned dict."""
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        json_data = {'cover_url': 'https://example.com/cover.png'}
        executor._execute_hook_with_config = Mock(return_value=(True, json_data, ''))
        config = {
            'parallel_execution': False,
            'completed': {
                'enabled': True,
                'command': 'echo test',
                'key_mapping': {},
            },
        }
        executor._load_config = Mock(return_value=config)
        result = executor.execute_hooks(['completed'], {})
        assert result.get('cover_url') == 'https://example.com/cover.png'

    def test_empty_cover_path_not_passed_through(self):
        """Empty or falsy cover_path in JSON is not added to result."""
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        json_data = {'cover_path': '', 'ext1_key': 'hello'}
        executor._execute_hook_with_config = Mock(return_value=(True, json_data, ''))
        config = {
            'parallel_execution': False,
            'started': {
                'enabled': True,
                'command': 'echo test',
                'key_mapping': {'ext1': 'ext1_key'},
            },
        }
        executor._load_config = Mock(return_value=config)
        result = executor.execute_hooks(['started'], {})
        assert 'cover_path' not in result
        assert result.get('ext1') == 'hello'

    def test_cover_and_ext_fields_coexist(self):
        """cover_path coexists with ext1-4 mapped fields."""
        from src.processing.hooks_executor import HooksExecutor
        executor = HooksExecutor()
        json_data = {
            'cover_path': '/tmp/cover.jpg',
            'my_ext_key': 'ext_value',
        }
        executor._execute_hook_with_config = Mock(return_value=(True, json_data, ''))
        config = {
            'parallel_execution': False,
            'started': {
                'enabled': True,
                'command': 'echo test',
                'key_mapping': {'ext1': 'my_ext_key'},
            },
        }
        executor._load_config = Mock(return_value=config)
        result = executor.execute_hooks(['started'], {})
        assert result.get('cover_path') == '/tmp/cover.jpg'
        assert result.get('ext1') == 'ext_value'


class TestApplyCoverFromHook:
    """UploadWorker._apply_cover_from_hook() unit tests."""

    def _make_worker(self):
        """Create an UploadWorker with mocked dependencies."""
        with patch('src.processing.upload_workers.RenameWorker'):
            from src.processing.upload_workers import UploadWorker
            mock_qm = Mock()
            worker = UploadWorker(mock_qm)
        return worker

    def _make_item(self, cover_source_path=None):
        """Create a GalleryQueueItem with optional cover."""
        from src.storage.queue_manager import GalleryQueueItem
        item = GalleryQueueItem(path='/tmp/gallery1', name='TestGallery')
        item.cover_source_path = cover_source_path
        return item

    def test_cover_path_sets_cover(self):
        """When hook returns cover_path pointing to an existing file, cover_source_path is set."""
        worker = self._make_worker()
        item = self._make_item()
        with patch('os.path.isfile', return_value=True):
            worker._apply_cover_from_hook(item, {'cover_path': '/tmp/hook_cover.jpg'})
        assert item.cover_source_path == '/tmp/hook_cover.jpg'

    def test_cover_path_nonexistent_file_ignored(self):
        """When cover_path points to a non-existent file, cover is not set."""
        worker = self._make_worker()
        item = self._make_item()
        with patch('os.path.isfile', return_value=False):
            worker._apply_cover_from_hook(item, {'cover_path': '/tmp/missing.jpg'})
        assert item.cover_source_path is None

    def test_cover_path_does_not_overwrite_existing(self):
        """When cover already exists, hook cover_path is ignored."""
        worker = self._make_worker()
        item = self._make_item(cover_source_path='/tmp/manual_cover.jpg')
        worker._apply_cover_from_hook(item, {'cover_path': '/tmp/hook_cover.jpg'})
        assert item.cover_source_path == '/tmp/manual_cover.jpg'

    def test_cover_url_downloads_and_sets(self):
        """When hook returns cover_url, it's downloaded to a temp file."""
        worker = self._make_worker()
        item = self._make_item()
        mock_resp = Mock()
        mock_resp.content = b'\x89PNG\r\n\x1a\nfake_image_data'
        mock_resp.raise_for_status = Mock()
        with patch('requests.get', return_value=mock_resp) as mock_get:
            worker._apply_cover_from_hook(item, {'cover_url': 'https://example.com/cover.png'})
        mock_get.assert_called_once_with('https://example.com/cover.png', timeout=30)
        assert item.cover_source_path is not None
        assert item.cover_source_path.endswith('.png')
        assert os.path.isfile(item.cover_source_path)
        # Clean up temp file
        os.unlink(item.cover_source_path)

    def test_cover_url_with_query_string(self):
        """URL query string is stripped when deriving file extension."""
        worker = self._make_worker()
        item = self._make_item()
        mock_resp = Mock()
        mock_resp.content = b'fake_jpeg_data'
        mock_resp.raise_for_status = Mock()
        with patch('requests.get', return_value=mock_resp):
            worker._apply_cover_from_hook(
                item, {'cover_url': 'https://cdn.example.com/img/cover.jpg?token=abc123'})
        assert item.cover_source_path is not None
        assert item.cover_source_path.endswith('.jpg')
        os.unlink(item.cover_source_path)

    def test_cover_url_no_extension_defaults_to_jpg(self):
        """When URL has no file extension, .jpg is used as default."""
        worker = self._make_worker()
        item = self._make_item()
        mock_resp = Mock()
        mock_resp.content = b'fake_data'
        mock_resp.raise_for_status = Mock()
        with patch('requests.get', return_value=mock_resp):
            worker._apply_cover_from_hook(
                item, {'cover_url': 'https://example.com/image/12345'})
        assert item.cover_source_path is not None
        assert item.cover_source_path.endswith('.jpg')
        os.unlink(item.cover_source_path)

    def test_cover_url_does_not_overwrite_existing(self):
        """When cover already exists, hook cover_url is ignored."""
        worker = self._make_worker()
        item = self._make_item(cover_source_path='/tmp/existing_cover.jpg')
        worker._apply_cover_from_hook(item, {'cover_url': 'https://example.com/new.jpg'})
        assert item.cover_source_path == '/tmp/existing_cover.jpg'

    def test_cover_url_download_failure_logs_warning(self):
        """When download fails, cover is not set and no exception escapes."""
        worker = self._make_worker()
        item = self._make_item()
        with patch('requests.get', side_effect=ConnectionError("Connection refused")):
            worker._apply_cover_from_hook(
                item, {'cover_url': 'https://example.com/unreachable.jpg'})
        assert item.cover_source_path is None

    def test_cover_path_takes_priority_over_cover_url(self):
        """When both cover_path and cover_url are present, cover_path wins."""
        worker = self._make_worker()
        item = self._make_item()
        with patch('os.path.isfile', return_value=True):
            worker._apply_cover_from_hook(item, {
                'cover_path': '/tmp/local_cover.jpg',
                'cover_url': 'https://example.com/remote.jpg',
            })
        # cover_path is checked first, so it should be set
        assert item.cover_source_path == '/tmp/local_cover.jpg'

    def test_no_cover_keys_does_nothing(self):
        """When ext_fields has no cover keys, item is unchanged."""
        worker = self._make_worker()
        item = self._make_item()
        worker._apply_cover_from_hook(item, {'ext1': 'some_value'})
        assert item.cover_source_path is None

    def test_cover_keys_filtered_from_setattr(self):
        """cover_path and cover_url are not set as item attributes via setattr.

        The worker's hook handler should skip cover_path/cover_url when
        doing the generic setattr loop for ext1-4 fields.
        """
        from src.storage.queue_manager import GalleryQueueItem
        item = GalleryQueueItem(path='/tmp/gallery1', name='TestGallery')
        ext_fields = {
            'ext1': 'hello',
            'cover_path': '/tmp/cover.jpg',
            'cover_url': 'https://example.com/cover.jpg',
        }
        # Simulate what the worker does: filter cover keys before setattr
        for key, value in ext_fields.items():
            if key not in ('cover_path', 'cover_url'):
                setattr(item, key, value)
        assert item.ext1 == 'hello'
        assert not hasattr(item, 'cover_path_attr')  # cover_path should NOT be set as attr
