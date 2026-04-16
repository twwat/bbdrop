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
