"""Unit tests for src/gui/widgets/video_sheet_utils.py."""
import hashlib
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Ensure Qt uses offscreen platform for headless testing
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage  # noqa: E402

from src.gui.widgets.video_sheet_utils import (  # noqa: E402
    get_cached_preview,
    resolve_sheet_path,
)


class TestResolveSheetPath:
    def test_uses_in_memory_path_when_file_exists(self, tmp_path):
        sheet = tmp_path / "sheet.png"
        sheet.write_bytes(b"x")
        item = SimpleNamespace(path="/g", screenshot_sheet_path=str(sheet))
        assert resolve_sheet_path(item) == str(sheet)

    def test_falls_back_to_md5_lookup_when_in_memory_missing(self, tmp_path):
        sheets_dir = tmp_path / "sheets"
        sheets_dir.mkdir()
        gallery_path = "/some/gallery"
        path_hash = hashlib.md5(gallery_path.encode()).hexdigest()[:12]
        expected = sheets_dir / f"{path_hash}.png"
        expected.write_bytes(b"x")

        item = SimpleNamespace(path=gallery_path, screenshot_sheet_path="")
        with patch("src.gui.widgets.video_sheet_utils.get_base_path",
                   return_value=str(tmp_path)):
            assert resolve_sheet_path(item) == str(expected)

    def test_falls_back_to_md5_lookup_when_in_memory_invalid(self, tmp_path):
        sheets_dir = tmp_path / "sheets"
        sheets_dir.mkdir()
        gallery_path = "/some/gallery"
        path_hash = hashlib.md5(gallery_path.encode()).hexdigest()[:12]
        expected = sheets_dir / f"{path_hash}.jpg"
        expected.write_bytes(b"x")

        item = SimpleNamespace(path=gallery_path,
                               screenshot_sheet_path="/nonexistent/file.png")
        with patch("src.gui.widgets.video_sheet_utils.get_base_path",
                   return_value=str(tmp_path)):
            assert resolve_sheet_path(item) == str(expected)

    def test_returns_empty_when_neither_source_exists(self, tmp_path):
        item = SimpleNamespace(path="/missing", screenshot_sheet_path="")
        with patch("src.gui.widgets.video_sheet_utils.get_base_path",
                   return_value=str(tmp_path)):
            assert resolve_sheet_path(item) == ""

    def test_png_takes_precedence_over_jpg(self, tmp_path):
        sheets_dir = tmp_path / "sheets"
        sheets_dir.mkdir()
        gallery_path = "/some/gallery"
        path_hash = hashlib.md5(gallery_path.encode()).hexdigest()[:12]
        png = sheets_dir / f"{path_hash}.png"
        jpg = sheets_dir / f"{path_hash}.jpg"
        png.write_bytes(b"png")
        jpg.write_bytes(b"jpg")

        item = SimpleNamespace(path=gallery_path, screenshot_sheet_path="")
        with patch("src.gui.widgets.video_sheet_utils.get_base_path",
                   return_value=str(tmp_path)):
            assert resolve_sheet_path(item) == str(png)

    def test_returns_empty_when_item_path_missing(self, tmp_path):
        item = SimpleNamespace(path="", screenshot_sheet_path="")
        with patch("src.gui.widgets.video_sheet_utils.get_base_path",
                   return_value=str(tmp_path)):
            assert resolve_sheet_path(item) == ""


def _write_test_png(path, width=800, height=600, color=0xFF0000):
    """Write a tiny solid-color PNG to disk for cache tests."""
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(color)
    img.save(str(path), "PNG")


class TestGetCachedPreview:
    def test_creates_scaled_preview_file(self, tmp_path):
        sheet = tmp_path / "sheet.png"
        _write_test_png(sheet, width=1280, height=720)
        cache_dir = tmp_path / "tooltips"

        result = get_cached_preview(str(sheet), target_width=640,
                                    cache_dir=str(cache_dir))
        assert result
        assert os.path.isfile(result)

        out = QImage(result)
        assert out.width() == 640
        assert out.height() == 360

    def test_reuses_cached_file_when_mtime_unchanged(self, tmp_path):
        sheet = tmp_path / "sheet.png"
        _write_test_png(sheet)
        cache_dir = tmp_path / "tooltips"

        first = get_cached_preview(str(sheet), 640, str(cache_dir))
        first_mtime = os.path.getmtime(first)

        second = get_cached_preview(str(sheet), 640, str(cache_dir))
        assert second == first
        assert os.path.getmtime(second) == first_mtime

    def test_regenerates_when_source_mtime_changes(self, tmp_path):
        sheet = tmp_path / "sheet.png"
        _write_test_png(sheet, color=0xFF0000)
        cache_dir = tmp_path / "tooltips"

        first = get_cached_preview(str(sheet), 640, str(cache_dir))
        first_source_mtime = os.path.getmtime(sheet)

        _write_test_png(sheet, color=0x00FF00)
        os.utime(sheet, (first_source_mtime + 10, first_source_mtime + 10))

        second = get_cached_preview(str(sheet), 640, str(cache_dir))
        # Because mtime is embedded in the cache filename, regeneration
        # produces a different path — both files exist on disk.
        assert second != first
        assert os.path.isfile(first)
        assert os.path.isfile(second)

    def test_separate_cache_file_per_width(self, tmp_path):
        sheet = tmp_path / "sheet.png"
        _write_test_png(sheet)
        cache_dir = tmp_path / "tooltips"

        a = get_cached_preview(str(sheet), 480, str(cache_dir))
        b = get_cached_preview(str(sheet), 640, str(cache_dir))
        assert a != b
        assert os.path.isfile(a)
        assert os.path.isfile(b)

    def test_returns_empty_for_invalid_source(self, tmp_path):
        cache_dir = tmp_path / "tooltips"
        assert get_cached_preview("/no/such/file.png", 640, str(cache_dir)) == ""
