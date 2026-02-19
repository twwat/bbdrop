#!/usr/bin/env python3
"""
pytest fixtures for unit tests in tests/unit/gui/

This conftest provides fixtures needed by settings_dialog tests and other
GUI unit tests in this directory.
"""

import os
import sys
import configparser
from pathlib import Path
from typing import Generator

import pytest

# Ensure Qt uses offscreen platform for headless testing
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")



# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


@pytest.fixture
def temp_config_dir(tmp_path) -> Generator[Path, None, None]:
    """
    Temporary configuration directory for testing.
    Creates a clean config directory that's cleaned up after tests.
    """
    config_dir = tmp_path / ".bbdrop"
    config_dir.mkdir(parents=True, exist_ok=True)
    yield config_dir


@pytest.fixture
def mock_config_file(temp_config_dir) -> Generator[Path, None, None]:
    """
    Create a temporary bbdrop.ini config file for testing.
    Returns path to the config file.
    """
    config_path = temp_config_dir / "bbdrop.ini"
    config = configparser.ConfigParser()

    config['credentials'] = {
        'username': 'testuser',
        'password': 'testpass',
        'api_key': 'testapikey',
    }

    config['templates'] = {
        'default': '[b]{name}[/b]',
    }

    config['SCANNING'] = {
        'fast_scanning': 'true',
        'sampling_method': '0',
        'sampling_fixed_count': '25',
        'sampling_percentage': '10',
        'exclude_first': 'false',
        'exclude_last': 'false',
        'exclude_small_images': 'false',
        'exclude_small_threshold': '50',
        'exclude_patterns': '',
        'exclude_outliers': 'false',
        'average_method': '1',
    }

    config['HOOKS'] = {
        'execution_mode': 'parallel',
        'added_enabled': 'false',
        'added_command': '',
        'added_show_console': 'false',
        'started_enabled': 'false',
        'started_command': '',
        'completed_enabled': 'false',
        'completed_command': '',
    }

    config['upload'] = {
        'timeout': '30',
        'retries': '3',
        'batch_size': '5',
    }

    with open(config_path, 'w') as f:
        config.write(f)

    yield config_path


@pytest.fixture
def mock_bbdrop_functions(monkeypatch, tmp_path):
    """
    Mock core bbdrop functions to avoid external dependencies.
    Patches common functions from the bbdrop module.
    """
    config_path = tmp_path / ".bbdrop"
    config_path.mkdir(parents=True, exist_ok=True)

    # Mock credential functions
    monkeypatch.setattr('bbdrop.get_credential', lambda x: None)
    monkeypatch.setattr('bbdrop.set_credential', lambda x, y: True)
    monkeypatch.setattr('bbdrop.remove_credential', lambda x: True)
    monkeypatch.setattr('bbdrop.encrypt_password', lambda x: f"encrypted_{x}")
    monkeypatch.setattr('bbdrop.decrypt_password', lambda x: x.replace("encrypted_", ""))

    # Mock path functions
    monkeypatch.setattr('bbdrop.get_config_path', lambda: str(config_path / "bbdrop.ini"))
    monkeypatch.setattr('bbdrop.get_project_root', lambda: str(tmp_path))
    monkeypatch.setattr('bbdrop.get_central_store_base_path', lambda: str(config_path))
    monkeypatch.setattr('bbdrop.get_default_central_store_base_path', lambda: str(config_path))
    monkeypatch.setattr('bbdrop.get_base_path', lambda: str(config_path))

    # Mock version function
    monkeypatch.setattr('bbdrop.get_version', lambda: '1.0.0-test')


@pytest.fixture
def default_settings():
    """Return default settings values for testing"""
    return {
        'max_retries': 3,
        'parallel_batch_size': 4,
        'upload_connect_timeout': 30,
        'upload_read_timeout': 90,
        'thumbnail_size': 4,
        'thumbnail_format': 2,
        'confirm_delete': True,
        'auto_rename': True,
        'auto_regenerate_bbcode': True,
        'auto_start_upload': False,
        'auto_clear_completed': False,
        'store_in_uploaded': True,
        'store_in_central': True,
    }


@pytest.fixture(autouse=True)
def mock_qmessagebox_for_unit_tests(monkeypatch):
    """
    CRITICAL: Mock QMessageBox to prevent modal dialogs from blocking test teardown.

    Many dialogs show confirmation messages in closeEvent, which blocks pytest-qt's
    internal _close_widgets() function during teardown.

    This fixture auto-returns Discard for all warning/question dialogs.
    """
    from PyQt6.QtWidgets import QMessageBox

    def mock_warning(*args, **kwargs):
        return QMessageBox.StandardButton.Discard

    def mock_question(*args, **kwargs):
        return QMessageBox.StandardButton.Yes

    def mock_information(*args, **kwargs):
        return QMessageBox.StandardButton.Ok

    def mock_critical(*args, **kwargs):
        return QMessageBox.StandardButton.Ok

    # Patch all static dialog methods
    monkeypatch.setattr(QMessageBox, 'warning', mock_warning)
    monkeypatch.setattr(QMessageBox, 'question', mock_question)
    monkeypatch.setattr(QMessageBox, 'information', mock_information)
    monkeypatch.setattr(QMessageBox, 'critical', mock_critical)

    yield


@pytest.fixture(autouse=True)
def auto_shutdown_bbdrop_windows():
    """Auto-shutdown any BBDropGUI instances after each test to prevent
    background threads from crashing xdist workers."""
    yield
    try:
        from src.gui.main_window import BBDropGUI
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                if isinstance(widget, BBDropGUI):
                    shutdown_bbdrop_window(widget)
    except Exception:
        pass


def shutdown_bbdrop_window(window):
    """Shut down BBDropGUI background threads to prevent fatal aborts.

    Call this in fixture teardown (after yield) for any test that
    instantiates BBDropGUI.
    """
    if hasattr(window, 'artifact_handler'):
        try:
            window.artifact_handler.stop()
        except Exception:
            pass
    if hasattr(window, 'queue_manager'):
        try:
            window.queue_manager.shutdown()
        except Exception:
            pass
    if hasattr(window, '_loader_thread') and window._loader_thread is not None:
        try:
            window._loader_thread.stop()
            window._loader_thread.wait(2000)
        except Exception:
            pass
