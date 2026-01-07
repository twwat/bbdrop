"""
Unit tests for StatisticsDialog

Tests statistics loading, file host table population, session time calculation,
and UI state management.
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import List

import pytest

# Ensure Qt uses offscreen platform for headless testing
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QTimer, QEventLoop
from PyQt6.QtWidgets import QApplication, QTableWidgetItem, QWidget

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))


class MockQtBot:
    """Simple mock for qtbot functionality without pytest-qt dependency."""

    def __init__(self, app: QApplication):
        self._app = app
        self._widgets: List[QWidget] = []

    def addWidget(self, widget: QWidget) -> None:
        """Track widget for cleanup."""
        self._widgets.append(widget)

    def wait(self, ms: int) -> None:
        """Wait for specified milliseconds, processing events."""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def cleanup(self) -> None:
        """Clean up tracked widgets."""
        for widget in self._widgets:
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                pass  # Widget already deleted
        self._widgets.clear()


@pytest.fixture(scope='session')
def qapp() -> QApplication:
    """Session-scoped Qt Application fixture."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def qtbot(qapp) -> MockQtBot:
    """Mock qtbot fixture for widget testing."""
    bot = MockQtBot(qapp)
    yield bot
    bot.cleanup()


@pytest.fixture
def mock_qsettings():
    """Mock QSettings to avoid writing to actual settings."""
    with patch('src.gui.dialogs.statistics_dialog.QSettings') as mock:
        settings_instance = MagicMock()
        mock.return_value = settings_instance
        # Default values for all settings
        settings_instance.value.side_effect = lambda key, default=None, **kwargs: {
            'app_startup_count': 10,
            'first_startup_timestamp': '2025-01-01 12:00:00',
            'total_session_time_seconds': 3600,
            'total_galleries': 50,
            'total_images': 500,
            'total_size_bytes_v2': '1073741824',  # 1 GiB
            'fastest_kbps': 1024.0,
            'fastest_kbps_timestamp': '2025-01-02 15:30:00',
            'checker_total_scans': 5,
            'checker_online_galleries': 40,
            'checker_partial_galleries': 5,
            'checker_offline_galleries': 5,
            'checker_online_images': 450,
            'checker_offline_images': 50,
        }.get(key, default)
        yield mock


@pytest.fixture
def mock_metrics_store():
    """Mock MetricsStore for file host statistics."""
    with patch('src.utils.metrics_store.get_metrics_store') as mock_get:
        mock_store = MagicMock()
        mock_get.return_value = mock_store
        mock_store.get_hosts_with_history.return_value = {
            'rapidgator': {
                'files_uploaded': 100,
                'files_failed': 5,
                'bytes_uploaded': 1073741824,  # 1 GiB
                'peak_speed': 5242880,  # 5 MiB/s in B/s
                'avg_speed': 2621440,   # 2.5 MiB/s in B/s
                'success_rate': 95.0,
            },
            'filedot': {
                'files_uploaded': 50,
                'files_failed': 2,
                'bytes_uploaded': 536870912,  # 512 MiB
                'peak_speed': 3145728,  # 3 MiB/s in B/s
                'avg_speed': 1572864,   # 1.5 MiB/s in B/s
                'success_rate': 96.2,
            },
        }
        yield mock_get, mock_store


@pytest.fixture
def dialog(qtbot, mock_qsettings, mock_metrics_store):
    """Create StatisticsDialog for testing with mocked dependencies."""
    from src.gui.dialogs.statistics_dialog import StatisticsDialog

    session_start = time.time() - 300  # 5 minutes ago
    dlg = StatisticsDialog(session_start_time=session_start)
    qtbot.addWidget(dlg)
    return dlg


class TestStatisticsDialogInitialization:
    """Test dialog initialization and setup."""

    def test_dialog_creation(self, dialog):
        """Test basic dialog creation."""
        assert dialog.windowTitle() == "Application Statistics"
        assert dialog.isModal()
        assert dialog.minimumWidth() == 700
        assert dialog.minimumHeight() == 420

    def test_has_tab_widget(self, dialog):
        """Test dialog has tabbed interface."""
        assert hasattr(dialog, '_tab_widget')
        assert dialog._tab_widget.count() == 2

    def test_tab_names(self, dialog):
        """Test tab names are correct."""
        assert dialog._tab_widget.tabText(0) == "General"
        assert dialog._tab_widget.tabText(1) == "File Hosts"


class TestFileHostStatsLoading:
    """Test _load_file_host_stats() functionality."""

    def test_load_file_host_stats_populates_table(self, dialog, mock_metrics_store):
        """Test table is populated with host data."""
        # Dialog loads stats in __init__, table should be populated
        table = dialog._file_hosts_table
        assert table.rowCount() == 2

    def test_load_file_host_stats_correct_order(self, dialog, mock_metrics_store):
        """Test hosts are sorted by files_uploaded descending."""
        table = dialog._file_hosts_table
        # Rapidgator has 100 files, filedot has 50 - rapidgator should be first
        first_host = table.item(0, 0).text()
        assert first_host == "Rapidgator"

    def test_load_file_host_stats_columns(self, dialog, mock_metrics_store):
        """Test table has correct column headers."""
        table = dialog._file_hosts_table
        assert table.columnCount() == 7
        headers = [table.horizontalHeaderItem(i).text() for i in range(7)]
        assert headers == ["Host", "Files", "Failed", "Data Uploaded",
                          "Peak Speed", "Avg Speed", "Success"]

    def test_load_file_host_stats_files_count(self, dialog, mock_metrics_store):
        """Test files uploaded count is displayed correctly."""
        table = dialog._file_hosts_table
        # Rapidgator row
        files_item = table.item(0, 1)
        assert files_item.text() == "100"

    def test_load_file_host_stats_failed_count(self, dialog, mock_metrics_store):
        """Test files failed count is displayed correctly."""
        table = dialog._file_hosts_table
        # Rapidgator row
        failed_item = table.item(0, 2)
        assert failed_item.text() == "5"

    def test_load_file_host_stats_data_size(self, dialog, mock_metrics_store):
        """Test data uploaded is formatted correctly."""
        table = dialog._file_hosts_table
        # Rapidgator row has 1 GiB
        data_item = table.item(0, 3)
        assert "GiB" in data_item.text() or "1.0" in data_item.text()

    def test_load_file_host_stats_peak_speed(self, dialog, mock_metrics_store):
        """Test peak speed is formatted correctly."""
        table = dialog._file_hosts_table
        # Rapidgator peak: 5 MiB/s (stored as B/s, converted to KiB/s for display)
        peak_item = table.item(0, 4)
        assert "MiB/s" in peak_item.text()

    def test_load_file_host_stats_avg_speed(self, dialog, mock_metrics_store):
        """Test average speed is formatted correctly."""
        table = dialog._file_hosts_table
        avg_item = table.item(0, 5)
        assert "MiB/s" in avg_item.text() or "KiB/s" in avg_item.text()

    def test_load_file_host_stats_success_rate(self, dialog, mock_metrics_store):
        """Test success rate is formatted as percentage."""
        table = dialog._file_hosts_table
        rate_item = table.item(0, 6)
        assert "%" in rate_item.text()
        assert "95.0" in rate_item.text()

    def test_load_file_host_stats_empty_data(self, qtbot, mock_qsettings):
        """Test table shows message when no file host data."""
        with patch('src.utils.metrics_store.get_metrics_store') as mock_get:
            mock_store = MagicMock()
            mock_get.return_value = mock_store
            mock_store.get_hosts_with_history.return_value = {}

            from src.gui.dialogs.statistics_dialog import StatisticsDialog
            dlg = StatisticsDialog()
            qtbot.addWidget(dlg)

            table = dlg._file_hosts_table
            assert table.rowCount() == 1
            item = table.item(0, 0)
            assert "No file host uploads" in item.text()

    def test_load_file_host_stats_import_error(self, qtbot, mock_qsettings):
        """Test table shows error message when metrics store unavailable."""
        with patch('src.utils.metrics_store.get_metrics_store') as mock_get:
            mock_get.side_effect = ImportError("MetricsStore not available")

            from src.gui.dialogs.statistics_dialog import StatisticsDialog
            dlg = StatisticsDialog()
            qtbot.addWidget(dlg)

            table = dlg._file_hosts_table
            assert table.rowCount() == 1
            item = table.item(0, 0)
            assert "Unable to load" in item.text()

    def test_load_file_host_stats_runtime_error(self, qtbot, mock_qsettings):
        """Test table handles RuntimeError gracefully."""
        with patch('src.utils.metrics_store.get_metrics_store') as mock_get:
            mock_get.side_effect = RuntimeError("Database locked")

            from src.gui.dialogs.statistics_dialog import StatisticsDialog
            dlg = StatisticsDialog()
            qtbot.addWidget(dlg)

            table = dlg._file_hosts_table
            assert table.rowCount() == 1
            item = table.item(0, 0)
            assert "Unable to load" in item.text()

    def test_load_file_host_stats_os_error(self, qtbot, mock_qsettings):
        """Test table handles OSError gracefully."""
        with patch('src.utils.metrics_store.get_metrics_store') as mock_get:
            mock_get.side_effect = OSError("File not found")

            from src.gui.dialogs.statistics_dialog import StatisticsDialog
            dlg = StatisticsDialog()
            qtbot.addWidget(dlg)

            table = dlg._file_hosts_table
            assert table.rowCount() == 1
            item = table.item(0, 0)
            assert "Unable to load" in item.text()


class TestSessionTimeCalculation:
    """Test session time calculations."""

    def test_session_time_includes_current_session(self, dialog):
        """Test total time includes current session duration."""
        # Dialog was created with session_start 5 minutes ago
        # Stored time is 3600s, current session ~300s
        # Total should be around 3900s
        label_text = dialog._total_time_label.text()
        # Should show at least "1h" for the stored time
        assert "h" in label_text or "m" in label_text

    def test_avg_session_length_calculated(self, dialog):
        """Test average session length is calculated from total/startups."""
        # With 10 startups and ~3900s total, avg should be ~390s (6.5 mins)
        label_text = dialog._avg_session_label.text()
        assert label_text != "0s"


class TestGeneralTabContent:
    """Test General tab content display."""

    def test_app_startups_displayed(self, dialog):
        """Test app startup count is displayed."""
        text = dialog._app_startups_label.text()
        assert text == "10"

    def test_first_startup_displayed(self, dialog):
        """Test first startup timestamp is displayed."""
        text = dialog._first_startup_label.text()
        assert "2025-01-01" in text

    def test_total_galleries_displayed(self, dialog):
        """Test total galleries count is displayed."""
        text = dialog._total_galleries_label.text()
        assert text == "50"

    def test_total_images_displayed(self, dialog):
        """Test total images count is displayed."""
        text = dialog._total_images_label.text()
        assert text == "500"

    def test_total_size_displayed(self, dialog):
        """Test total data size is formatted and displayed."""
        text = dialog._total_size_label.text()
        assert "GiB" in text or "MiB" in text

    def test_fastest_speed_displayed(self, dialog):
        """Test fastest speed is displayed."""
        text = dialog._fastest_speed_label.text()
        assert "KiB/s" in text or "MiB/s" in text

    def test_scanner_stats_displayed(self, dialog):
        """Test scanner statistics are displayed."""
        assert dialog._total_scans_label.text() == "5"
        assert dialog._online_galleries_label.text() == "40"
        assert dialog._partial_galleries_label.text() == "5"
        assert dialog._offline_galleries_label.text() == "5"


class TestDialogButtons:
    """Test dialog button functionality."""

    def test_close_button_exists(self, dialog):
        """Test close button is present in dialog."""
        # Find the button box
        from PyQt6.QtWidgets import QDialogButtonBox
        button_boxes = dialog.findChildren(QDialogButtonBox)
        assert len(button_boxes) == 1

        # Check it has Close button
        button_box = button_boxes[0]
        assert button_box.button(QDialogButtonBox.StandardButton.Close) is not None

    def test_close_button_closes_dialog(self, dialog, qtbot):
        """Test clicking close button closes dialog."""
        from PyQt6.QtWidgets import QDialogButtonBox
        button_box = dialog.findChildren(QDialogButtonBox)[0]
        close_btn = button_box.button(QDialogButtonBox.StandardButton.Close)

        # Track if dialog was closed
        closed = []
        dialog.rejected.connect(lambda: closed.append(True))

        close_btn.click()

        assert len(closed) == 1


class TestCenterOnParent:
    """Test dialog centering behavior."""

    def test_center_on_parent_with_parent(self, qtbot, mock_qsettings, mock_metrics_store):
        """Test dialog centers on parent widget."""
        from src.gui.dialogs.statistics_dialog import StatisticsDialog
        from PyQt6.QtWidgets import QMainWindow

        parent = QMainWindow()
        parent.setGeometry(100, 100, 800, 600)
        qtbot.addWidget(parent)
        parent.show()

        dlg = StatisticsDialog(parent=parent)
        qtbot.addWidget(dlg)

        # Dialog should be positioned relative to parent
        parent_center_x = parent.x() + parent.width() // 2
        dialog_center_x = dlg.x() + dlg.width() // 2

        # Should be roughly centered (within 50 pixels due to frame geometry)
        assert abs(parent_center_x - dialog_center_x) < 50

    def test_center_on_screen_without_parent(self, dialog):
        """Test dialog centers on screen when no parent."""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            screen_center_x = screen.geometry().width() // 2
            dialog_center_x = dialog.x() + dialog.width() // 2
            # Should be roughly centered on screen
            assert abs(screen_center_x - dialog_center_x) < 100
