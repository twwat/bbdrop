"""Tests for video artifact path."""
import os
from unittest.mock import patch


class TestVideoArtifactsPath:
    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/home/user/.bbdrop')
    def test_video_artifacts_path_is_under_videos(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        path = get_video_artifacts_path()
        # Use os.path.join to build expected path (platform-aware)
        expected = os.path.join('/home/user/.bbdrop', 'videos')
        assert path == expected
        # Check it ends with 'videos' using os.sep for platform awareness
        assert path.endswith(f"{os.sep}videos") or path.endswith("/videos")

    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/home/user/.bbdrop')
    def test_creates_directory(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        get_video_artifacts_path()
        # Build expected path using os.path.join (platform-aware)
        expected = os.path.join('/home/user/.bbdrop', 'videos')
        mock_makedirs.assert_any_call(expected, exist_ok=True)

    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/custom/path')
    def test_respects_custom_base_path(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        path = get_video_artifacts_path()
        # Use os.path.join to build expected path (platform-aware)
        expected = os.path.join('/custom/path', 'videos')
        assert path == expected

    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/home/user/.bbdrop')
    def test_returns_string(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        path = get_video_artifacts_path()
        assert isinstance(path, str)
