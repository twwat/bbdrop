from unittest.mock import patch, MagicMock
from src.processing.hooks_executor import HooksExecutor


class TestPlainTextExtraction:
    """Test that URL[n]/PATH[n] placeholders resolve from plain-text stdout."""

    def _make_executor_with_config(self, hook_type, key_mappings, stdout):
        """Helper: create executor, mock config and subprocess."""
        executor = HooksExecutor()

        config = {
            'parallel_execution': False,
            hook_type: {
                'enabled': True,
                'command': 'test_cmd',
                'show_console': False,
                'key_mapping': key_mappings,
            },
        }
        context = {'gallery_path': '/test', 'gallery_name': 'test'}

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = stdout
        mock_result.stderr = ''

        with patch.object(executor, '_load_config', return_value=config), \
             patch('subprocess.run', return_value=mock_result), \
             patch('shlex.split', return_value=['test_cmd']):
            return executor.execute_hooks([hook_type], context)

    def test_url_placeholder_from_plain_text(self):
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'URL[1]'},
            'Download: https://example.com/file.zip\n'
        )
        assert result.get('ext1') == 'https://example.com/file.zip'

    def test_url_with_component(self):
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'URL[1]', 'ext2': 'URL[1].filename'},
            'https://example.com/uploads/photo.jpg\n'
        )
        assert result.get('ext1') == 'https://example.com/uploads/photo.jpg'
        assert result.get('ext2') == 'photo.jpg'

    def test_path_placeholder(self):
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'PATH[1]'},
            'Output saved to C:\\Users\\me\\result.txt\n'
        )
        assert result.get('ext1') == 'C:\\Users\\me\\result.txt'

    def test_negative_index(self):
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'URL[-1]'},
            'https://first.com/a.zip\nhttps://second.com/b.zip\n'
        )
        assert result.get('ext1') == 'https://second.com/b.zip'

    def test_json_still_works(self):
        """JSON extraction should still work as before."""
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'download_url'},
            '{"download_url": "https://example.com/file.zip"}\n'
        )
        assert result.get('ext1') == 'https://example.com/file.zip'

    def test_unresolvable_placeholder_skipped(self):
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'URL[5]'},
            'https://example.com/only-one.zip\n'
        )
        assert 'ext1' not in result

    def test_json_key_preferred_over_placeholder(self):
        """When stdout is valid JSON, JSON keys should be used even if placeholder matches."""
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'url'},
            '{"url": "https://json-value.com/file.zip"}\n'
        )
        assert result.get('ext1') == 'https://json-value.com/file.zip'

    def test_mixed_json_and_placeholder(self):
        """JSON key for one ext, placeholder for another — both resolve."""
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'url', 'ext2': 'URL[1]'},
            '{"url": "https://json-value.com/file.zip"}\n'
        )
        assert result.get('ext1') == 'https://json-value.com/file.zip'
        # URL[1] still resolves — plain-text detection runs on raw stdout regardless
        assert result.get('ext2') == 'https://json-value.com/file.zip'

    def test_url_extension_component(self):
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'URL[1].ext'},
            'https://example.com/uploads/photo.jpg\n'
        )
        assert result.get('ext1') == '.jpg'

    def test_url_domain_component(self):
        result = self._make_executor_with_config(
            'completed',
            {'ext1': 'URL[1].domain'},
            'https://example.com/uploads/photo.jpg\n'
        )
        assert result.get('ext1') == 'example.com'
