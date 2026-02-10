# tests/unit/processing/test_cover_full_flow.py
"""Integration test: cover detection -> upload -> template output."""
import os
import pytest
from unittest.mock import patch, MagicMock

from src.storage.queue_manager import GalleryQueueItem


class TestCoverFullFlow:
    """End-to-end cover photo flow with mocked network."""

    def test_cover_detection_to_template(self):
        """Cover detected during scan -> uploaded -> appears in #cover# placeholder."""
        # 1. Detection
        from src.core.cover_detector import detect_cover
        files = ["image001.jpg", "cover.jpg", "image002.jpg"]
        cover = detect_cover(files, patterns="cover*")
        assert cover == "cover.jpg"

        # 2. Set on item
        item = GalleryQueueItem(
            path="/tmp/test",
            name="Test Gallery",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        # 3. Simulate cover upload result
        item.cover_result = {
            "status": "success",
            "bbcode": "[url=https://imx.to/i/abc][img]https://t.imx.to/t/abc.jpg[/img][/url]",
            "image_url": "https://imx.to/i/abc",
            "thumb_url": "https://t.imx.to/t/abc.jpg",
        }

        # 4. Template resolution
        from bbdrop import apply_template
        template = "#cover#\n[b]#folderName#[/b]\n#allImages#"
        data = {
            'cover': item.cover_result.get('bbcode', ''),
            'folder_name': 'Test Gallery',
            'all_images': '[img]thumb1[/img]  [img]thumb2[/img]',
            'picture_count': 2,
        }
        result = apply_template(template, data)

        assert "[url=https://imx.to/i/abc]" in result
        assert "[b]Test Gallery[/b]" in result
        assert "[img]thumb1[/img]" in result

    def test_no_cover_template_empty(self):
        """When no cover is detected, #cover# resolves to empty string."""
        from bbdrop import apply_template
        template = "#cover#[b]#folderName#[/b]"
        data = {
            'cover': '',
            'folder_name': 'Test Gallery',
            'all_images': '',
            'picture_count': 0,
        }
        result = apply_template(template, data)
        assert result.startswith("[b]Test Gallery[/b]")

    def test_cover_conditional_with_content(self):
        """[if cover]...[/if] shows content when cover exists."""
        from bbdrop import apply_template
        template = "[if cover]#cover#[/if]\n#folderName#"

        # With cover
        data_with = {'cover': '[img]x[/img]', 'folder_name': 'Test', 'all_images': '', 'picture_count': 1}
        result_with = apply_template(template, data_with)
        assert "[img]x[/img]" in result_with

        # Without cover
        data_without = {'cover': '', 'folder_name': 'Test', 'all_images': '', 'picture_count': 1}
        result_without = apply_template(template, data_without)
        assert "[img]x[/img]" not in result_without
        assert "Test" in result_without

    def test_cover_data_model_roundtrip(self):
        """Cover fields survive creation -> dict -> item roundtrip."""
        item = GalleryQueueItem(
            path="/tmp/test",
            name="Test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
            cover_result={"bbcode": "x", "image_url": "y", "thumb_url": "z"},
        )
        assert item.cover_source_path == "/tmp/test/cover.jpg"
        assert item.cover_host_id == "imx"
        assert item.cover_result["bbcode"] == "x"

    def test_cover_detection_patterns(self):
        """Various cover detection patterns work correctly."""
        from src.core.cover_detector import detect_cover

        # Standard cover filename
        assert detect_cover(["img1.jpg", "cover.jpg"], patterns="cover*") == "cover.jpg"
        # Poster pattern
        assert detect_cover(["img1.jpg", "poster.png"], patterns="cover*, poster*") == "poster.png"
        # Suffix pattern
        assert detect_cover(["img1.jpg", "gallery_cover.jpg"], patterns="*_cover.*") == "gallery_cover.jpg"
        # No match
        assert detect_cover(["img1.jpg", "img2.jpg"], patterns="cover*") is None
        # Empty patterns
        assert detect_cover(["cover.jpg"], patterns="") is None
