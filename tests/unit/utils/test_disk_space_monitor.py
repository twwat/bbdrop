"""Tests for DiskSpaceMonitor tier logic and adaptive polling."""

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from src.utils.disk_space_monitor import DiskSpaceMonitor


def _make_usage(free_bytes):
    """Helper to create a mock disk_usage result."""
    return type('Usage', (), {
        'total': 1_000_000_000_000,
        'used': 1_000_000_000_000 - free_bytes,
        'free': free_bytes,
    })()


@pytest.fixture
def temp_dirs():
    with tempfile.TemporaryDirectory() as data_dir:
        with tempfile.TemporaryDirectory() as temp_dir:
            yield data_dir, temp_dir


@pytest.fixture
def monitor(temp_dirs):
    data_dir, temp_dir = temp_dirs
    with patch('src.utils.disk_space_monitor.QTimer'):
        mon = DiskSpaceMonitor(
            data_dir=data_dir,
            temp_dir=temp_dir,
            warning_mb=2048,
            critical_mb=512,
            emergency_mb=100,
        )
        yield mon


class TestTierCalculation:
    """Tier is determined by the lower free space of monitored paths."""

    def test_ok_when_both_above_warning(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(5_000_000_000)):  # 5 GB
            monitor._poll()
            assert monitor.current_tier == "ok"

    def test_warning_when_below_warning_threshold(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(1_500_000_000)):  # 1.5 GB
            monitor._poll()
            assert monitor.current_tier == "warning"

    def test_critical_when_below_critical_threshold(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(300_000_000)):  # 300 MB
            monitor._poll()
            assert monitor.current_tier == "critical"

    def test_emergency_when_below_emergency_threshold(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(50_000_000)):  # 50 MB
            monitor._poll()
            assert monitor.current_tier == "emergency"

    def test_tier_uses_lower_of_two_paths(self, monitor):
        """If paths are on different devices, tier is determined by the worse one."""
        monitor._same_device = False
        calls = [
            _make_usage(5_000_000_000),  # data dir: 5 GB (ok)
            _make_usage(300_000_000),     # temp dir: 300 MB (critical)
        ]
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   side_effect=calls):
            monitor._poll()
            assert monitor.current_tier == "critical"


class TestAdaptivePolling:
    """Poll interval adjusts based on current tier."""

    def test_comfortable_interval(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(10_000_000_000)):  # 10 GB
            monitor._poll()
            assert monitor._current_interval_ms == 60_000

    def test_approaching_interval(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(3_000_000_000)):  # 3 GB (between 2x warning and warning)
            monitor._poll()
            assert monitor._current_interval_ms == 15_000

    def test_danger_interval(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(1_000_000_000)):  # 1 GB (between warning and critical)
            monitor._poll()
            assert monitor._current_interval_ms == 5_000

    def test_emergency_interval(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(50_000_000)):  # 50 MB
            monitor._poll()
            assert monitor._current_interval_ms == 2_000


class TestGatingAPI:
    """Public API for upload pipeline to check before starting work."""

    def test_can_start_upload_true_when_ok(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(5_000_000_000)):
            monitor._poll()
            assert monitor.can_start_upload() is True

    def test_can_start_upload_false_when_critical(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(300_000_000)):
            monitor._poll()
            assert monitor.can_start_upload() is False

    def test_can_create_archive_checks_temp_free(self, monitor):
        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(1_000_000_000)):  # 1 GB free
            monitor._poll()
            # 500 MB archive + 512 MB critical margin = 1012 MB needed, have 1000 MB
            assert monitor.can_create_archive(500_000_000) is False
            # 200 MB archive + 512 MB critical margin = 712 MB needed, have 1000 MB
            assert monitor.can_create_archive(200_000_000) is True


class TestTierChangedSignal:
    """tier_changed signal emitted only on actual transitions."""

    def test_signal_emitted_on_tier_change(self, monitor):
        handler = MagicMock()
        monitor.tier_changed.connect(handler)

        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(5_000_000_000)):
            monitor._poll()  # ok

        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(300_000_000)):
            monitor._poll()  # critical

        # Should have been called for the ok->critical transition
        handler.assert_called_with("critical")

    def test_no_signal_when_tier_unchanged(self, monitor):
        handler = MagicMock()

        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(5_000_000_000)):
            monitor._poll()  # ok

        monitor.tier_changed.connect(handler)

        with patch('src.utils.disk_space_monitor.shutil.disk_usage',
                   return_value=_make_usage(5_000_000_000)):
            monitor._poll()  # still ok

        handler.assert_not_called()
