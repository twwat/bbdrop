"""Tests that the engine excludes cover-only files from the gallery upload."""
import os
from unittest.mock import MagicMock

from src.core.engine import UploadEngine


class TestEngineCoverExclusion:
    """Engine skips cover file when exclude_from_gallery is set."""

    def _make_mock_uploader(self):
        """Create a mock uploader with all required ABC methods."""
        mock_uploader = MagicMock()
        mock_uploader.config = MagicMock()
        mock_uploader.config.max_file_size_mb = None
        mock_uploader.supports_gallery_rename.return_value = False
        mock_uploader.sanitize_gallery_name.side_effect = lambda n: n
        mock_uploader.get_gallery_url.return_value = "https://imx.to/g/test"
        mock_uploader.get_thumbnail_url.return_value = "https://t.imx.to/t/test.jpg"

        # upload_image returns success for each file
        mock_uploader.upload_image.return_value = {
            'status': 'success',
            'data': {
                'image_url': 'https://imx.to/i/test',
                'thumb_url': 'https://t.imx.to/t/test.jpg',
                'gallery_id': 'gal1',
                'original_filename': 'img.jpg',
            }
        }
        return mock_uploader

    def test_cover_file_excluded_from_upload(self, tmp_path):
        """When exclude_cover_file is passed, that file is not uploaded as gallery image."""
        # Create dummy images
        for name in ["image001.jpg", "image002.jpg", "cover.jpg"]:
            (tmp_path / name).write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)

        mock_uploader = self._make_mock_uploader()
        engine = UploadEngine(mock_uploader)
        engine.run(
            folder_path=str(tmp_path),
            gallery_name="test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=0,
            parallel_batch_size=1,
            template_name="default",
            exclude_cover_file="cover.jpg",
        )

        # cover.jpg should NOT have been uploaded
        for call_args in mock_uploader.upload_image.call_args_list:
            args, kwargs = call_args
            # First positional arg is the image path
            file_path = args[0] if args else ''
            assert 'cover.jpg' not in str(file_path), \
                f"cover.jpg should have been excluded but was uploaded: {file_path}"

        # Only image001.jpg and image002.jpg should have been uploaded
        assert mock_uploader.upload_image.call_count == 2

    def test_no_exclusion_when_param_none(self, tmp_path):
        """When exclude_cover_file is None, all files are uploaded."""
        for name in ["image001.jpg", "cover.jpg"]:
            (tmp_path / name).write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)

        mock_uploader = self._make_mock_uploader()
        engine = UploadEngine(mock_uploader)
        engine.run(
            folder_path=str(tmp_path),
            gallery_name="test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=0,
            parallel_batch_size=1,
            template_name="default",
        )

        # Both files should have been uploaded
        assert mock_uploader.upload_image.call_count == 2

    def test_no_exclusion_when_param_empty_string(self, tmp_path):
        """When exclude_cover_file is empty string, all files are uploaded."""
        for name in ["image001.jpg", "cover.jpg"]:
            (tmp_path / name).write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)

        mock_uploader = self._make_mock_uploader()
        engine = UploadEngine(mock_uploader)
        engine.run(
            folder_path=str(tmp_path),
            gallery_name="test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=0,
            parallel_batch_size=1,
            template_name="default",
            exclude_cover_file="",
        )

        # Both files should have been uploaded
        assert mock_uploader.upload_image.call_count == 2

    def test_exclude_only_matching_filename(self, tmp_path):
        """Exclusion only removes the exact filename, not partial matches."""
        for name in ["cover.jpg", "my_cover.jpg", "cover2.jpg"]:
            (tmp_path / name).write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)

        mock_uploader = self._make_mock_uploader()
        engine = UploadEngine(mock_uploader)
        engine.run(
            folder_path=str(tmp_path),
            gallery_name="test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=0,
            parallel_batch_size=1,
            template_name="default",
            exclude_cover_file="cover.jpg",
        )

        # Only cover.jpg excluded; my_cover.jpg and cover2.jpg should upload
        assert mock_uploader.upload_image.call_count == 2

        uploaded_basenames = []
        for call_args in mock_uploader.upload_image.call_args_list:
            args, kwargs = call_args
            file_path = args[0] if args else ''
            uploaded_basenames.append(os.path.basename(file_path))

        assert "cover.jpg" not in uploaded_basenames
        assert "my_cover.jpg" in uploaded_basenames
        assert "cover2.jpg" in uploaded_basenames

    def test_cover_excluded_from_total_count(self, tmp_path):
        """When cover is excluded, total_images in results should reflect that."""
        for name in ["image001.jpg", "image002.jpg", "cover.jpg"]:
            (tmp_path / name).write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)

        mock_uploader = self._make_mock_uploader()
        engine = UploadEngine(mock_uploader)
        results = engine.run(
            folder_path=str(tmp_path),
            gallery_name="test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=0,
            parallel_batch_size=1,
            template_name="default",
            exclude_cover_file="cover.jpg",
        )

        # The engine should report 2 total images, not 3
        assert results['total_images'] == 2
        assert results['successful_count'] == 2

    def test_cover_file_not_in_folder_is_harmless(self, tmp_path):
        """If exclude_cover_file names a file that doesn't exist, nothing breaks."""
        for name in ["image001.jpg", "image002.jpg"]:
            (tmp_path / name).write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)

        mock_uploader = self._make_mock_uploader()
        engine = UploadEngine(mock_uploader)
        engine.run(
            folder_path=str(tmp_path),
            gallery_name="test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=0,
            parallel_batch_size=1,
            template_name="default",
            exclude_cover_file="nonexistent_cover.jpg",
        )

        # All 2 files should still upload fine
        assert mock_uploader.upload_image.call_count == 2
