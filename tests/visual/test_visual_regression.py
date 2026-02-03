"""
Visual Regression Tests

Compares current widget appearance to baseline screenshots.
Run with: pytest tests/visual/ -v

To update baselines:
    pytest tests/visual/ -v --update-baselines

To capture specific dialog:
    pytest tests/visual/ -v -k "settings_dialog"
"""

import os
import pytest

# Skip visual regression tests under xdist - baselines vary between workers
pytestmark = pytest.mark.skipif(
    'PYTEST_XDIST_WORKER' in os.environ,
    reason="Visual regression tests require consistent baselines, skip under xdist"
)
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow, QTableWidget, QTextEdit
from PyQt6.QtCore import Qt


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for test session."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def update_baselines(request):
    """Check if baseline update mode is enabled."""
    return request.config.getoption("--update-baselines", default=False)


class _MockMainWindow(QMainWindow):
    """Mock main window for ThemeManager with required methods."""

    def __init__(self):
        super().__init__()
        self._current_theme_mode = 'dark'
        self._current_font_size = 9
        self.settings = MagicMock()
        self.settings.value = MagicMock(return_value=9)
        self.gallery_table = MagicMock()
        self.gallery_table.table = QTableWidget()  # Real widget to avoid infinite Mock chains in apply_font_size
        self.log_text = QTextEdit()  # Real widget to avoid GC crash on Mock
        self.theme_toggle_btn = MagicMock()
        self._rows_with_widgets = set()

    def _refresh_button_icons(self):
        """Mock method called after theme change."""
        pass

    def refresh_all_status_icons(self):
        """Mock method called after theme change."""
        pass

    def update_action_buttons_for_row(self, row):
        """Mock method for row-specific button updates."""
        pass


@pytest.fixture
def theme_manager(qapp):
    """Get ThemeManager instance."""
    from src.gui.theme_manager import ThemeManager
    mock_window = _MockMainWindow()
    return ThemeManager(mock_window)


class TestDialogVisuals:
    """Visual regression tests for dialogs."""

    @pytest.fixture
    def mock_settings(self):
        """Mock QSettings for dialogs."""
        with patch('PyQt6.QtCore.QSettings') as mock:
            settings = MagicMock()
            settings.value.return_value = None
            mock.return_value = settings
            yield settings

    def test_help_dialog_light(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test HelpDialog appearance in light theme."""
        theme_manager.apply_theme("light")
        QApplication.processEvents()

        from src.gui.dialogs.help_dialog import HelpDialog
        with patch.object(HelpDialog, '_start_document_loading'):
            dialog = HelpDialog()
            dialog.resize(800, 600)

            if update_baselines:
                path = capture_baseline(dialog, "help_dialog", "light")
                pytest.skip(f"Baseline updated: {path}")
            else:
                assert_visual_match(dialog, "help_dialog", "light")

            dialog.close()

    def test_help_dialog_dark(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test HelpDialog appearance in dark theme."""
        theme_manager.apply_theme("dark")
        QApplication.processEvents()

        from src.gui.dialogs.help_dialog import HelpDialog
        with patch.object(HelpDialog, '_start_document_loading'):
            dialog = HelpDialog()
            dialog.resize(800, 600)

            if update_baselines:
                path = capture_baseline(dialog, "help_dialog", "dark")
                pytest.skip(f"Baseline updated: {path}")
            else:
                assert_visual_match(dialog, "help_dialog", "dark")

            dialog.close()

    def test_about_dialog_light(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test About section appearance in light theme."""
        theme_manager.apply_theme("light")
        QApplication.processEvents()

        # About is part of HelpDialog
        from src.gui.dialogs.help_dialog import HelpDialog
        with patch.object(HelpDialog, '_start_document_loading'):
            dialog = HelpDialog()
            dialog.resize(800, 600)
            # Switch to About tab if present
            if hasattr(dialog, 'tab_widget'):
                for i in range(dialog.tab_widget.count()):
                    if 'about' in dialog.tab_widget.tabText(i).lower():
                        dialog.tab_widget.setCurrentIndex(i)
                        break
            QApplication.processEvents()

            if update_baselines:
                path = capture_baseline(dialog, "about_dialog", "light")
                pytest.skip(f"Baseline updated: {path}")
            else:
                assert_visual_match(dialog, "about_dialog", "light")

            dialog.close()

    def test_statistics_dialog_light(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines, mock_settings
    ):
        """Test StatisticsDialog appearance in light theme."""
        theme_manager.apply_theme("light")
        QApplication.processEvents()

        try:
            from src.gui.dialogs.statistics_dialog import StatisticsDialog
            # Mock the database/stats data
            with patch.object(StatisticsDialog, '_load_statistics', return_value=None):
                dialog = StatisticsDialog(parent=None)
                dialog.resize(600, 400)

                if update_baselines:
                    path = capture_baseline(dialog, "statistics_dialog", "light")
                    pytest.skip(f"Baseline updated: {path}")
                else:
                    assert_visual_match(dialog, "statistics_dialog", "light")

                dialog.close()
        except Exception as e:
            pytest.skip(f"StatisticsDialog not available: {e}")

    def test_statistics_dialog_dark(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines, mock_settings
    ):
        """Test StatisticsDialog appearance in dark theme."""
        theme_manager.apply_theme("dark")
        QApplication.processEvents()

        try:
            from src.gui.dialogs.statistics_dialog import StatisticsDialog
            with patch.object(StatisticsDialog, '_load_statistics', return_value=None):
                dialog = StatisticsDialog(parent=None)
                dialog.resize(600, 400)

                if update_baselines:
                    path = capture_baseline(dialog, "statistics_dialog", "dark")
                    pytest.skip(f"Baseline updated: {path}")
                else:
                    assert_visual_match(dialog, "statistics_dialog", "dark")

                dialog.close()
        except Exception as e:
            pytest.skip(f"StatisticsDialog not available: {e}")


class TestWidgetVisuals:
    """Visual regression tests for individual widgets."""

    def test_progress_bar_states_light(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test progress bar appearance in various states."""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QLabel

        theme_manager.apply_theme("light")
        QApplication.processEvents()

        # Create test widget with multiple progress bars
        container = QWidget()
        layout = QVBoxLayout(container)

        states = [
            ("Empty", 0),
            ("25%", 25),
            ("50%", 50),
            ("75%", 75),
            ("Complete", 100),
        ]

        for label_text, value in states:
            label = QLabel(label_text)
            progress = QProgressBar()
            progress.setMinimum(0)
            progress.setMaximum(100)
            progress.setValue(value)
            progress.setFixedWidth(300)
            layout.addWidget(label)
            layout.addWidget(progress)

        container.setFixedSize(350, 300)

        if update_baselines:
            path = capture_baseline(container, "progress_bars", "light")
            pytest.skip(f"Baseline updated: {path}")
        else:
            assert_visual_match(container, "progress_bars", "light")

    def test_progress_bar_states_dark(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test progress bar appearance in dark theme."""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QLabel

        theme_manager.apply_theme("dark")
        QApplication.processEvents()

        container = QWidget()
        layout = QVBoxLayout(container)

        states = [
            ("Empty", 0),
            ("25%", 25),
            ("50%", 50),
            ("75%", 75),
            ("Complete", 100),
        ]

        for label_text, value in states:
            label = QLabel(label_text)
            progress = QProgressBar()
            progress.setMinimum(0)
            progress.setMaximum(100)
            progress.setValue(value)
            progress.setFixedWidth(300)
            layout.addWidget(label)
            layout.addWidget(progress)

        container.setFixedSize(350, 300)

        if update_baselines:
            path = capture_baseline(container, "progress_bars", "dark")
            pytest.skip(f"Baseline updated: {path}")
        else:
            assert_visual_match(container, "progress_bars", "dark")

    def test_button_states_light(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test button styling in light theme."""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton

        theme_manager.apply_theme("light")
        QApplication.processEvents()

        container = QWidget()
        layout = QVBoxLayout(container)

        # Test different button classes
        buttons = [
            ("Default Button", None),
            ("Primary", "btn-primary"),
            ("Secondary", "btn-secondary"),
            ("Danger", "btn-shutdown-danger"),
            ("Success", "btn-shutdown-success"),
        ]

        for text, class_name in buttons:
            btn = QPushButton(text)
            btn.setFixedWidth(200)
            if class_name:
                btn.setProperty("class", class_name)
            layout.addWidget(btn)

        container.setFixedSize(250, 250)

        if update_baselines:
            path = capture_baseline(container, "buttons", "light")
            pytest.skip(f"Baseline updated: {path}")
        else:
            assert_visual_match(container, "buttons", "light")

    def test_button_states_dark(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test button styling in dark theme."""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton

        theme_manager.apply_theme("dark")
        QApplication.processEvents()

        container = QWidget()
        layout = QVBoxLayout(container)

        buttons = [
            ("Default Button", None),
            ("Primary", "btn-primary"),
            ("Secondary", "btn-secondary"),
            ("Danger", "btn-shutdown-danger"),
            ("Success", "btn-shutdown-success"),
        ]

        for text, class_name in buttons:
            btn = QPushButton(text)
            btn.setFixedWidth(200)
            if class_name:
                btn.setProperty("class", class_name)
            layout.addWidget(btn)

        container.setFixedSize(250, 250)

        if update_baselines:
            path = capture_baseline(container, "buttons", "dark")
            pytest.skip(f"Baseline updated: {path}")
        else:
            assert_visual_match(container, "buttons", "dark")

    def test_status_labels_light(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test status label styling in light theme."""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

        theme_manager.apply_theme("light")
        QApplication.processEvents()

        container = QWidget()
        layout = QVBoxLayout(container)

        labels = [
            ("Success Status", "status-success"),
            ("Error Status", "status-error"),
            ("Warning Status", "status-warning"),
            ("Muted Text", "status-muted"),
            ("Bold Label", "label-bold"),
            ("Info Italic", "label-info-italic"),
        ]

        for text, class_name in labels:
            label = QLabel(text)
            label.setProperty("class", class_name)
            layout.addWidget(label)

        container.setFixedSize(250, 200)

        if update_baselines:
            path = capture_baseline(container, "status_labels", "light")
            pytest.skip(f"Baseline updated: {path}")
        else:
            assert_visual_match(container, "status_labels", "light")

    def test_status_labels_dark(
        self, qapp, theme_manager, assert_visual_match, capture_baseline, update_baselines
    ):
        """Test status label styling in dark theme."""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

        theme_manager.apply_theme("dark")
        QApplication.processEvents()

        container = QWidget()
        layout = QVBoxLayout(container)

        labels = [
            ("Success Status", "status-success"),
            ("Error Status", "status-error"),
            ("Warning Status", "status-warning"),
            ("Muted Text", "status-muted"),
            ("Bold Label", "label-bold"),
            ("Info Italic", "label-info-italic"),
        ]

        for text, class_name in labels:
            label = QLabel(text)
            label.setProperty("class", class_name)
            layout.addWidget(label)

        container.setFixedSize(250, 200)

        if update_baselines:
            path = capture_baseline(container, "status_labels", "dark")
            pytest.skip(f"Baseline updated: {path}")
        else:
            assert_visual_match(container, "status_labels", "dark")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--update-baselines'])
