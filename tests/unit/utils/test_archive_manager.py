"""Tests for raw video passthrough in ArchiveManager."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.archive_manager import ArchiveManager


class TestVideoPassthrough:
    """Tests for media_type='video' passthrough behavior."""

    def test_raw_video_returns_single_file_path(self):
        """A single video file in a folder is returned directly without archiving."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "test.mp4"
            video_path.write_bytes(b'\x00' * 1024)

            manager = ArchiveManager()
            result = manager.create_or_reuse_archive(
                db_id=1,
                folder_path=Path(tmpdir),
                gallery_name="test",
                media_type="video",
            )
            assert len(result) == 1
            assert result[0].suffix == '.mp4'
            assert result[0] == video_path

    def test_video_passthrough_for_mkv(self):
        """MKV files are also returned via passthrough."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "test.mkv"
            video_path.write_bytes(b'\x00' * 1024)

            manager = ArchiveManager()
            result = manager.create_or_reuse_archive(
                db_id=2,
                folder_path=Path(tmpdir),
                gallery_name="test",
                media_type="video",
            )
            assert len(result) == 1
            assert result[0].name == "test.mkv"

    def test_video_passthrough_multiple_files(self):
        """Multiple video files in a folder are all returned sorted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("clip_b.avi", "clip_a.mp4", "clip_c.webm"):
                (Path(tmpdir) / name).write_bytes(b'\x00' * 512)

            manager = ArchiveManager()
            result = manager.create_or_reuse_archive(
                db_id=3,
                folder_path=Path(tmpdir),
                gallery_name="multi",
                media_type="video",
            )
            assert len(result) == 3
            names = [p.name for p in result]
            assert names == sorted(names)

    def test_video_passthrough_ignores_non_video_files(self):
        """Non-video files in the folder are not included in passthrough."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "movie.mp4").write_bytes(b'\x00' * 1024)
            (Path(tmpdir) / "thumb.jpg").write_bytes(b'\xff' * 512)
            (Path(tmpdir) / "notes.txt").write_bytes(b'hello')

            manager = ArchiveManager()
            result = manager.create_or_reuse_archive(
                db_id=4,
                folder_path=Path(tmpdir),
                gallery_name="mixed",
                media_type="video",
            )
            assert len(result) == 1
            assert result[0].name == "movie.mp4"

    def test_video_passthrough_skips_cache(self):
        """Video passthrough does not populate the archive cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.mp4").write_bytes(b'\x00' * 1024)

            manager = ArchiveManager()
            manager.create_or_reuse_archive(
                db_id=5,
                folder_path=Path(tmpdir),
                gallery_name="test",
                media_type="video",
            )
            assert 5 not in manager.archive_cache

    def test_video_passthrough_returns_original_paths(self):
        """Returned paths point to the original files, not copies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "original.mov"
            video_path.write_bytes(b'\x00' * 2048)

            manager = ArchiveManager()
            result = manager.create_or_reuse_archive(
                db_id=6,
                folder_path=Path(tmpdir),
                gallery_name="test",
                media_type="video",
            )
            assert result[0].resolve() == video_path.resolve()

    def test_video_passthrough_case_insensitive_extension(self):
        """Video extension matching is case-insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.MP4").write_bytes(b'\x00' * 1024)
            (Path(tmpdir) / "test2.Mkv").write_bytes(b'\x00' * 1024)

            manager = ArchiveManager()
            result = manager.create_or_reuse_archive(
                db_id=7,
                folder_path=Path(tmpdir),
                gallery_name="test",
                media_type="video",
            )
            assert len(result) == 2

    def test_video_with_split_creates_archive(self):
        """When split_size_mb > 0, video galleries are archived normally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "gallery"
            folder.mkdir()
            # Put image files so the archive creation path works
            (folder / "img.jpg").write_bytes(b'\xff\xd8' + b'\x00' * 1024)

            manager = ArchiveManager(temp_dir=Path(tmpdir) / "archives")
            result = manager.create_or_reuse_archive(
                db_id=8,
                folder_path=folder,
                gallery_name="split_test",
                media_type="video",
                split_size_mb=100,
            )
            # Should fall through to normal archive creation (ZIP)
            assert len(result) == 1
            assert result[0].suffix == '.zip'

    def test_image_media_type_unchanged(self):
        """Default media_type='image' still creates archives as before."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "gallery"
            folder.mkdir()
            (folder / "photo.jpg").write_bytes(b'\xff\xd8' + b'\x00' * 1024)

            manager = ArchiveManager(temp_dir=Path(tmpdir) / "archives")
            result = manager.create_or_reuse_archive(
                db_id=9,
                folder_path=folder,
                gallery_name="normal",
                media_type="image",
            )
            assert len(result) == 1
            assert result[0].suffix == '.zip'

    def test_default_media_type_is_image(self):
        """Omitting media_type defaults to 'image' (backward compatible)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "gallery"
            folder.mkdir()
            (folder / "photo.jpg").write_bytes(b'\xff\xd8' + b'\x00' * 1024)

            manager = ArchiveManager(temp_dir=Path(tmpdir) / "archives")
            # Call without media_type -- should behave like image
            result = manager.create_or_reuse_archive(
                db_id=10,
                folder_path=folder,
                gallery_name="compat",
            )
            assert len(result) == 1
            assert result[0].suffix == '.zip'

    def test_video_no_files_falls_through_to_archive(self):
        """If video folder has no video files, falls through to archive path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "empty_video"
            folder.mkdir()
            # Only image files, no video files
            (folder / "img.jpg").write_bytes(b'\xff\xd8' + b'\x00' * 512)

            manager = ArchiveManager(temp_dir=Path(tmpdir) / "archives")
            result = manager.create_or_reuse_archive(
                db_id=11,
                folder_path=folder,
                gallery_name="fallback",
                media_type="video",
            )
            # Falls through to normal ZIP creation using image files
            assert len(result) == 1
            assert result[0].suffix == '.zip'

    def test_video_empty_folder_raises(self):
        """Empty folder with media_type='video' raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "empty"
            folder.mkdir()

            manager = ArchiveManager(temp_dir=Path(tmpdir) / "archives")
            with pytest.raises(ValueError, match="No image files found"):
                manager.create_or_reuse_archive(
                    db_id=12,
                    folder_path=folder,
                    gallery_name="empty",
                    media_type="video",
                )

    def test_video_all_supported_extensions(self):
        """All VIDEO_EXTENSIONS are recognized by passthrough."""
        from src.core.constants import VIDEO_EXTENSIONS

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, ext in enumerate(VIDEO_EXTENSIONS):
                (Path(tmpdir) / f"file{i}{ext}").write_bytes(b'\x00' * 256)

            manager = ArchiveManager()
            result = manager.create_or_reuse_archive(
                db_id=13,
                folder_path=Path(tmpdir),
                gallery_name="all_exts",
                media_type="video",
            )
            assert len(result) == len(VIDEO_EXTENSIONS)


class TestGetVideoFiles:
    """Tests for the _get_video_files helper method."""

    def test_returns_sorted_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("z.mp4", "a.mp4", "m.mp4"):
                (Path(tmpdir) / name).write_bytes(b'\x00' * 64)

            manager = ArchiveManager()
            result = manager._get_video_files(Path(tmpdir))
            names = [p.name for p in result]
            assert names == ["a.mp4", "m.mp4", "z.mp4"]

    def test_nonexistent_folder_raises(self):
        manager = ArchiveManager()
        with pytest.raises(FileNotFoundError):
            manager._get_video_files(Path("/nonexistent/path"))

    def test_file_not_directory_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "file.txt"
            f.write_text("hello")

            manager = ArchiveManager()
            with pytest.raises(ValueError, match="not a directory"):
                manager._get_video_files(f)

    def test_empty_folder_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ArchiveManager()
            result = manager._get_video_files(Path(tmpdir))
            assert result == []

    def test_ignores_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "subdir.mp4").mkdir()  # directory named like video
            (Path(tmpdir) / "real.mp4").write_bytes(b'\x00' * 64)

            manager = ArchiveManager()
            result = manager._get_video_files(Path(tmpdir))
            assert len(result) == 1
            assert result[0].name == "real.mp4"
