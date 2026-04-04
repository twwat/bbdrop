"""Tests for new config setting defaults."""
import pytest
from unittest.mock import patch, MagicMock


class TestImageHostNewDefaults:
    """New image host settings should have hardcoded defaults."""

    def test_auto_retry_default(self):
        from src.core.image_host_config import _HARDCODED_DEFAULTS
        assert 'auto_retry' in _HARDCODED_DEFAULTS
        assert _HARDCODED_DEFAULTS['auto_retry'] is True

    def test_max_upload_time_default(self):
        from src.core.image_host_config import _HARDCODED_DEFAULTS
        assert 'max_upload_time' in _HARDCODED_DEFAULTS
        assert _HARDCODED_DEFAULTS['max_upload_time'] == 0

    def test_max_file_size_mb_default(self):
        from src.core.image_host_config import _HARDCODED_DEFAULTS
        assert 'max_file_size_mb' in _HARDCODED_DEFAULTS
        assert _HARDCODED_DEFAULTS['max_file_size_mb'] == 0


class TestFileHostNewDefaults:
    """File host should have connect_timeout default."""

    def test_connect_timeout_default(self):
        from src.core.file_host_config import _HARDCODED_DEFAULTS
        assert 'connect_timeout' in _HARDCODED_DEFAULTS
        assert _HARDCODED_DEFAULTS['connect_timeout'] == 30


class TestImageHostJsonDefaults:
    """Image host JSON configs should include new defaults."""

    def test_imx_max_file_size(self):
        import json
        with open('assets/image_hosts/imx.json') as f:
            config = json.load(f)
        assert config.get('max_file_size_mb') == 100

    def test_turbo_max_file_size(self):
        import json
        with open('assets/image_hosts/turbo.json') as f:
            config = json.load(f)
        assert config.get('max_file_size_mb') == 35

    def test_pixhost_max_file_size(self):
        import json
        with open('assets/image_hosts/pixhost.json') as f:
            config = json.load(f)
        assert config.get('max_file_size_mb') == 10

    def test_imx_auto_retry_default(self):
        import json
        with open('assets/image_hosts/imx.json') as f:
            config = json.load(f)
        assert config['defaults'].get('auto_retry') is True

    def test_imx_max_upload_time_default(self):
        import json
        with open('assets/image_hosts/imx.json') as f:
            config = json.load(f)
        assert config['defaults'].get('max_upload_time') == 0
