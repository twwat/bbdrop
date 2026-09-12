#!/usr/bin/env python3
"""Tests for template_utils file host link formatting."""

import pytest
from unittest.mock import Mock, patch


class TestGetFileHostLinksForTemplate:
    """Test get_file_host_links_for_template with #fileSize# placeholder."""

    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filesize_placeholder_single_part(self, mock_setting, mock_config_mgr):
        """#fileSize# is replaced with formatted file size."""
        from src.utils.template_utils import get_file_host_links_for_template

        mock_store = Mock()
        mock_store.get_file_host_uploads.return_value = [{
            'host_name': 'rapidgator',
            'status': 'completed',
            'download_url': 'https://rapidgator.net/file/abc',
            'part_number': 0,
            'file_size': 262_144_000,  # 250 MiB
        }]

        host_config = Mock()
        host_config.name = "Rapidgator"
        mock_config_mgr.return_value.hosts = {'rapidgator': host_config}
        mock_setting.return_value = "[url=#link#]#hostName# (#fileSize#)[/url]"

        result = get_file_host_links_for_template(mock_store, "/path/gallery")
        assert result == "[url=https://rapidgator.net/file/abc]Rapidgator (250.0\u00a0MiB)[/url]"

    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filesize_placeholder_multi_part(self, mock_setting, mock_config_mgr):
        """#fileSize# shows per-part size, not total."""
        from src.utils.template_utils import get_file_host_links_for_template

        mock_store = Mock()
        mock_store.get_file_host_uploads.return_value = [
            {
                'host_name': 'rapidgator',
                'status': 'completed',
                'download_url': 'https://rapidgator.net/file/abc',
                'part_number': 0,
                'file_size': 262_144_000,
            },
            {
                'host_name': 'rapidgator',
                'status': 'completed',
                'download_url': 'https://rapidgator.net/file/def',
                'part_number': 1,
                'file_size': 131_072_000,
            },
        ]

        host_config = Mock()
        host_config.name = "Rapidgator"
        mock_config_mgr.return_value.hosts = {'rapidgator': host_config}
        mock_setting.return_value = "[url=#link#]#hostName# - #partLabel# (#fileSize#)[/url]"

        result = get_file_host_links_for_template(mock_store, "/path/gallery")
        lines = result.split("\n")
        assert len(lines) == 2
        assert "(250.0\u00a0MiB)" in lines[0]
        assert "(125.0\u00a0MiB)" in lines[1]

    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filesize_placeholder_null_file_size(self, mock_setting, mock_config_mgr):
        """#fileSize# resolves to empty string when file_size is NULL."""
        from src.utils.template_utils import get_file_host_links_for_template

        mock_store = Mock()
        mock_store.get_file_host_uploads.return_value = [{
            'host_name': 'rapidgator',
            'status': 'completed',
            'download_url': 'https://rapidgator.net/file/abc',
            'part_number': 0,
            'file_size': None,
        }]

        host_config = Mock()
        host_config.name = "Rapidgator"
        mock_config_mgr.return_value.hosts = {'rapidgator': host_config}
        mock_setting.return_value = "[url=#link#]#hostName# (#fileSize#)[/url]"

        result = get_file_host_links_for_template(mock_store, "/path/gallery")
        assert result == "[url=https://rapidgator.net/file/abc]Rapidgator ()[/url]"

    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_no_bbcode_format_returns_raw_url(self, mock_setting, mock_config_mgr):
        """No bbcode_format configured returns raw URL (no fileSize substitution)."""
        from src.utils.template_utils import get_file_host_links_for_template

        mock_store = Mock()
        mock_store.get_file_host_uploads.return_value = [{
            'host_name': 'rapidgator',
            'status': 'completed',
            'download_url': 'https://rapidgator.net/file/abc',
            'part_number': 0,
            'file_size': 262_144_000,
        }]

        host_config = Mock()
        host_config.name = "Rapidgator"
        mock_config_mgr.return_value.hosts = {'rapidgator': host_config}
        mock_setting.return_value = ""

        result = get_file_host_links_for_template(mock_store, "/path/gallery")
        assert result == "https://rapidgator.net/file/abc"

    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filename_placeholder_full(self, mock_setting, mock_config_mgr):
        """#fileName# is replaced with the full uploaded filename including extension."""
        from src.utils.template_utils import get_file_host_links_for_template

        mock_store = Mock()
        mock_store.get_file_host_uploads.return_value = [{
            'host_name': 'rapidgator',
            'status': 'completed',
            'download_url': 'https://rapidgator.net/file/abc',
            'part_number': 0,
            'file_size': 262_144_000,
            'file_name': 'Gallery.part1.rar',
        }]

        host_config = Mock()
        host_config.name = "Rapidgator"
        mock_config_mgr.return_value.hosts = {'rapidgator': host_config}
        mock_setting.return_value = "[url=#link#]#fileName#[/url]"

        result = get_file_host_links_for_template(mock_store, "/path/gallery")
        assert result == "[url=https://rapidgator.net/file/abc]Gallery.part1.rar[/url]"

    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filename_basename_and_ext_placeholders(self, mock_setting, mock_config_mgr):
        """#fileBaseName# strips the extension; #fileExt# is the extension without the dot, lowercased."""
        from src.utils.template_utils import get_file_host_links_for_template

        mock_store = Mock()
        mock_store.get_file_host_uploads.return_value = [{
            'host_name': 'rapidgator',
            'status': 'completed',
            'download_url': 'https://rapidgator.net/file/abc',
            'part_number': 0,
            'file_size': 262_144_000,
            'file_name': 'Gallery.part1.RAR',
        }]

        host_config = Mock()
        host_config.name = "Rapidgator"
        mock_config_mgr.return_value.hosts = {'rapidgator': host_config}
        mock_setting.return_value = "#fileBaseName# . #fileExt#"

        result = get_file_host_links_for_template(mock_store, "/path/gallery")
        assert result == "Gallery.part1 . rar"

    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filename_placeholders_empty_when_file_name_missing(self, mock_setting, mock_config_mgr):
        """All three filename placeholders resolve to empty when file_name is missing."""
        from src.utils.template_utils import get_file_host_links_for_template

        mock_store = Mock()
        mock_store.get_file_host_uploads.return_value = [{
            'host_name': 'rapidgator',
            'status': 'completed',
            'download_url': 'https://rapidgator.net/file/abc',
            'part_number': 0,
            'file_size': 262_144_000,
            # 'file_name' intentionally omitted
        }]

        host_config = Mock()
        host_config.name = "Rapidgator"
        mock_config_mgr.return_value.hosts = {'rapidgator': host_config}
        mock_setting.return_value = "[#fileName#|#fileBaseName#|#fileExt#]"

        result = get_file_host_links_for_template(mock_store, "/path/gallery")
        assert result == "[||]"


class TestFilenamePlaceholderCaseInsensitivity:
    """Filename tokens must resolve regardless of the case the user typed.

    Older host configs (and the built-in defaults shipped before the
    camelCase convention landed) use lowercase `#filename#`. That token
    collides with the video contact-sheet `#filename#` in apply_template,
    which blanks it for image galleries. Consuming it here -- before
    apply_template runs -- fixes both spellings without touching the INI.
    """

    def _store(self, file_name, part_number=0, extra=None):
        rows = [{
            'host_name': 'filedot',
            'status': 'completed',
            'download_url': 'https://filedot.to/abc',
            'part_number': part_number,
            'file_size': 1024,
            'file_name': file_name,
        }]
        if extra:
            rows.extend(extra)
        store = Mock()
        store.get_file_host_uploads.return_value = rows
        return store

    @pytest.mark.unit
    @pytest.mark.parametrize("token", ["#fileName#", "#filename#", "#FileName#"])
    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filename_token_any_case(self, mock_setting, mock_config_mgr, token):
        """All casings of the filename token resolve to the uploaded name."""
        from src.utils.template_utils import get_file_host_links_for_template

        host_config = Mock()
        host_config.name = "Filedot"
        mock_config_mgr.return_value.hosts = {'filedot': host_config}
        mock_setting.return_value = f"[url=#link#]{token}[/url]"

        store = self._store('Gallery.zip')
        result = get_file_host_links_for_template(store, "/path/gallery")
        assert result == "[url=https://filedot.to/abc]Gallery.zip[/url]"

    @pytest.mark.unit
    @pytest.mark.parametrize("token,expected", [
        ("#fileBaseName#", "Gallery.part1"),
        ("#filebasename#", "Gallery.part1"),
        ("#fileExt#", "rar"),
        ("#fileext#", "rar"),
    ])
    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_basename_and_ext_tokens_any_case(self, mock_setting, mock_config_mgr,
                                              token, expected):
        """#fileBaseName# / #fileExt# are also case-insensitive."""
        from src.utils.template_utils import get_file_host_links_for_template

        host_config = Mock()
        host_config.name = "Filedot"
        mock_config_mgr.return_value.hosts = {'filedot': host_config}
        mock_setting.return_value = f"[{token}]"

        store = self._store('Gallery.part1.rar')
        result = get_file_host_links_for_template(store, "/path/gallery")
        assert result == f"[{expected}]"

    @pytest.mark.unit
    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_filename_token_does_not_eat_basename_token(self, mock_setting, mock_config_mgr):
        """#fileName# must not match inside #fileBaseName#."""
        from src.utils.template_utils import get_file_host_links_for_template

        host_config = Mock()
        host_config.name = "Filedot"
        mock_config_mgr.return_value.hosts = {'filedot': host_config}
        mock_setting.return_value = "#filename#|#filebasename#|#fileext#"

        store = self._store('Gallery.part1.rar')
        result = get_file_host_links_for_template(store, "/path/gallery")
        assert result == "Gallery.part1.rar|Gallery.part1|rar"

    @pytest.mark.unit
    @patch('src.utils.template_utils.get_config_manager')
    @patch('src.utils.template_utils.get_file_host_setting')
    def test_split_archive_uses_per_part_filename(self, mock_setting, mock_config_mgr):
        """Split archives resolve each part's own filename, non-split the single one."""
        from src.utils.template_utils import get_file_host_links_for_template

        host_config = Mock()
        host_config.name = "Filedot"
        mock_config_mgr.return_value.hosts = {'filedot': host_config}
        mock_setting.return_value = "#filename#"

        store = self._store('Gallery.part1.rar', part_number=0, extra=[{
            'host_name': 'filedot',
            'status': 'completed',
            'download_url': 'https://filedot.to/def',
            'part_number': 1,
            'file_size': 1024,
            'file_name': 'Gallery.part2.rar',
        }])
        result = get_file_host_links_for_template(store, "/path/gallery")
        assert result.split("\n") == ["Gallery.part1.rar", "Gallery.part2.rar"]

    @pytest.mark.unit
    def test_backslash_in_value_is_literal(self):
        """A backslash in the value must not be read as a regex backreference.

        Tested against the helper directly: os.path.basename strips at the
        backslash on Windows, so this can't be driven end-to-end there, but
        the substitution must stay literal on every platform.
        """
        from src.utils.template_utils import _sub_token

        assert _sub_token('#fileName#', 'fileName', r'Odd\1Name.zip') == r'Odd\1Name.zip'
        assert _sub_token('#fileName#', 'fileName', r'A\g<0>B') == r'A\g<0>B'
