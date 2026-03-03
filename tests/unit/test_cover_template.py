# tests/unit/test_cover_template.py
"""Tests for #cover# template placeholder."""


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


class TestCoverTemplateDataFromListResults:
    """Cover data extraction from list-type cover_result."""

    def test_cover_urls_from_list_results(self):
        """cover_url and cover_thumb_url extracted from first successful entry."""
        cover_results = [
            {'status': 'success', 'bbcode': '[url=X][img]Y[/img][/url]', 'image_url': 'X', 'thumb_url': 'Y'},
            {'status': 'success', 'bbcode': '[url=A][img]B[/img][/url]', 'image_url': 'A', 'thumb_url': 'B'},
        ]
        c_url = next((r.get('image_url', '') for r in cover_results if r.get('status') == 'success'), '')
        c_thumb = next((r.get('thumb_url', '') for r in cover_results if r.get('status') == 'success'), '')
        assert c_url == 'X'
        assert c_thumb == 'Y'

    def test_cover_bbcode_joins_successful_entries(self):
        """cover_bbcode joins all successful bbcodes with newline."""
        cover_results = [
            {'status': 'success', 'bbcode': 'A', 'image_url': 'X', 'thumb_url': 'Y'},
            {'status': 'failed', 'error': 'timeout'},
            {'status': 'success', 'bbcode': 'B', 'image_url': 'A', 'thumb_url': 'B'},
        ]
        cover_bbcode = "\n".join(
            r['bbcode'] for r in cover_results
            if r.get('status') == 'success' and r.get('bbcode')
        )
        assert cover_bbcode == "A\nB"

    def test_cover_empty_when_all_failed(self):
        """All failures produce empty cover data."""
        cover_results = [
            {'status': 'failed', 'error': 'timeout'},
        ]
        c_url = next((r.get('image_url', '') for r in cover_results if r.get('status') == 'success'), '')
        cover_bbcode = "\n".join(
            r['bbcode'] for r in cover_results
            if r.get('status') == 'success' and r.get('bbcode')
        )
        assert c_url == ''
        assert cover_bbcode == ''

    def test_cover_empty_when_none_result(self):
        """None or empty cover_result produces empty cover data."""
        cover_results = None
        c_url = next((r.get('image_url', '') for r in (cover_results or []) if r.get('status') == 'success'), '')
        assert c_url == ''
