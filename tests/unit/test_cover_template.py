# tests/unit/test_cover_template.py
"""Tests for #cover# template placeholder."""
import pytest


class TestCoverPlaceholder:
    """#cover# placeholder resolves correctly in templates."""

    def test_cover_placeholder_replaced(self):
        from bbdrop import apply_template
        data = {
            'folder_name': 'Test Gallery',
            'all_images': '[img]thumb[/img]',
            'cover': '[url=full][img]cover_thumb[/img][/url]',
            'picture_count': 5,
        }
        template = "#cover#\n#folderName#\n#allImages#"
        result = apply_template(template, data)
        assert "[url=full][img]cover_thumb[/img][/url]" in result

    def test_cover_placeholder_empty_when_no_cover(self):
        from bbdrop import apply_template
        data = {
            'folder_name': 'Test Gallery',
            'all_images': '[img]thumb[/img]',
            'cover': '',
            'picture_count': 5,
        }
        template = "#cover#\n#folderName#"
        result = apply_template(template, data)
        # #cover# should become empty string, so result starts with newline then folderName
        assert "Test Gallery" in result

    def test_cover_conditional_true(self):
        from bbdrop import apply_template
        data = {
            'folder_name': 'Test',
            'all_images': '',
            'cover': '[img]thumb[/img]',
            'picture_count': 1,
        }
        template = "[if cover]Cover: #cover#[/if]"
        result = apply_template(template, data)
        assert "Cover: [img]thumb[/img]" in result

    def test_cover_conditional_false(self):
        from bbdrop import apply_template
        data = {
            'folder_name': 'Test',
            'all_images': '',
            'cover': '',
            'picture_count': 1,
        }
        template = "[if cover]Cover: #cover#[/if]\n#folderName#"
        result = apply_template(template, data)
        assert "Cover:" not in result
        assert "Test" in result
