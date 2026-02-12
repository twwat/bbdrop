"""Tests that cover detection has sensible defaults out of the box."""
import pytest
from unittest.mock import patch, MagicMock


class TestCoverDefaults:
    """Cover detection defaults detect common cover filenames without config."""

    def test_default_patterns_detect_cover_file(self):
        from src.core.cover_detector import detect_cover
        from src.core.constants import DEFAULT_COVER_PATTERNS
        files = ["image001.jpg", "image002.jpg", "cover.jpg", "image003.jpg"]
        result = detect_cover(files, patterns=DEFAULT_COVER_PATTERNS)
        assert result == "cover.jpg"

    def test_default_patterns_detect_poster_file(self):
        from src.core.cover_detector import detect_cover
        from src.core.constants import DEFAULT_COVER_PATTERNS
        files = ["image001.jpg", "poster.png", "image002.jpg"]
        result = detect_cover(files, patterns=DEFAULT_COVER_PATTERNS)
        assert result == "poster.png"

    def test_default_patterns_no_false_positives(self):
        from src.core.cover_detector import detect_cover
        from src.core.constants import DEFAULT_COVER_PATTERNS
        files = ["image001.jpg", "image002.jpg", "photo.png", "landscape.jpg"]
        result = detect_cover(files, patterns=DEFAULT_COVER_PATTERNS)
        assert result is None

    def test_queue_manager_uses_default_patterns(self):
        from src.storage.queue_manager import QueueManager
        from src.core.constants import DEFAULT_COVER_PATTERNS
        with patch('src.storage.queue_manager.QueueStore'), \
             patch('src.storage.queue_manager.QSettings') as MockSettings, \
             patch('src.storage.queue_manager.QObject.__init__'):
            mock_settings = MockSettings.return_value
            mock_settings.value.side_effect = lambda key, default, **kw: default
            qm = QueueManager.__new__(QueueManager)
            config = qm._get_cover_detection_config()
            assert config['patterns'] == DEFAULT_COVER_PATTERNS
            assert config['patterns'] != ''
