"""Tests for video artifact path."""
from unittest.mock import patch


class TestVideoArtifactsPath:
    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/home/user/.bbdrop')
    def test_video_artifacts_path_is_under_videos(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        path = get_video_artifacts_path()
        assert path.endswith("/videos")
        assert path == "/home/user/.bbdrop/videos"

    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/home/user/.bbdrop')
    def test_creates_directory(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        get_video_artifacts_path()
        mock_makedirs.assert_any_call('/home/user/.bbdrop/videos', exist_ok=True)

    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/custom/path')
    def test_respects_custom_base_path(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        path = get_video_artifacts_path()
        assert path == "/custom/path/videos"

    @patch('src.utils.paths.os.makedirs')
    @patch('src.utils.paths.get_central_store_base_path', return_value='/home/user/.bbdrop')
    def test_returns_string(self, mock_base, mock_makedirs):
        from src.utils.paths import get_video_artifacts_path

        path = get_video_artifacts_path()
        assert isinstance(path, str)
