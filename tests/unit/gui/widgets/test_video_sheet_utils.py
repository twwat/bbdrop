"""Unit tests for src/gui/widgets/video_sheet_utils.py."""
import hashlib
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.gui.widgets.video_sheet_utils import resolve_sheet_path


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
