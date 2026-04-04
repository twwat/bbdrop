"""Tests for ConnectionTestDialog."""
import pytest


class TestConnectionTestDialogStructure:
    """ConnectionTestDialog should have the right structure."""

    def test_class_exists(self):
        from src.gui.dialogs.connection_test_dialog import ConnectionTestDialog
        assert ConnectionTestDialog is not None

    def test_has_test_button(self):
        with open("src/gui/dialogs/connection_test_dialog.py") as f:
            content = f.read()
        assert "Run Test" in content

    def test_has_four_result_labels(self):
        with open("src/gui/dialogs/connection_test_dialog.py") as f:
            content = f.read()
        assert "test_credentials_label" in content
        assert "test_userinfo_label" in content
        assert "test_upload_label" in content
        assert "test_delete_label" in content

    def test_has_error_label(self):
        with open("src/gui/dialogs/connection_test_dialog.py") as f:
            content = f.read()
        assert "test_error_label" in content

    def test_has_update_result_method(self):
        with open("src/gui/dialogs/connection_test_dialog.py") as f:
            content = f.read()
        assert "def update_result" in content

    def test_has_set_all_running_method(self):
        with open("src/gui/dialogs/connection_test_dialog.py") as f:
            content = f.read()
        assert "def set_all_running" in content
