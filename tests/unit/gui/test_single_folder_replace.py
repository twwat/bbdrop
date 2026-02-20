"""Test that _add_single_folder calls both remove_item and _remove_gallery_from_table."""

import os
import pytest
import tempfile
from unittest.mock import Mock, patch, MagicMock

from src.gui.gallery_queue_controller import GalleryQueueController
from src.storage.queue_manager import GalleryQueueItem
from src.core.constants import QUEUE_STATE_READY


@pytest.fixture
def temp_gallery():
    with tempfile.TemporaryDirectory() as tmpdir:
        gallery = os.path.join(tmpdir, "test_gallery")
        os.makedirs(gallery)
        yield gallery


@pytest.fixture
def mock_main_window(temp_gallery):
    mw = Mock()
    # Simulate an existing item in queue
    existing = GalleryQueueItem(
        path=temp_gallery, name="test_gallery", status=QUEUE_STATE_READY
    )
    mw.queue_manager.get_item.return_value = existing
    mw.queue_manager.remove_item.return_value = True
    mw.queue_manager.add_item.return_value = True
    mw.template_combo.currentText.return_value = "default"
    mw.gallery_table.current_tab = "Main"
    mw._get_default_host.return_value = "imx"
    mw._remove_gallery_from_table = Mock()
    mw._add_gallery_to_table = Mock()
    mw._check_if_gallery_exists.return_value = []
    return mw


class TestSingleFolderReplace:
    """_add_single_folder must remove table row when replacing."""

    @patch('src.gui.gallery_queue_controller.QMessageBox')
    def test_replace_calls_remove_from_table(self, mock_msgbox_class, mock_main_window, temp_gallery):
        """When user confirms replace, both queue and table removal should happen."""
        # Simulate user clicking "Yes" to replace
        mock_msgbox_instance = mock_msgbox_class.return_value
        mock_msgbox_instance.exec.return_value = mock_msgbox_class.StandardButton.Yes

        controller = GalleryQueueController(mock_main_window)
        controller._add_single_folder(temp_gallery)

        mock_main_window.queue_manager.remove_item.assert_called_once_with(temp_gallery)
        mock_main_window._remove_gallery_from_table.assert_called_once_with(temp_gallery)

    @patch('src.gui.gallery_queue_controller.QMessageBox')
    def test_decline_replace_skips_both(self, mock_msgbox_class, mock_main_window, temp_gallery):
        """When user declines replace, neither removal should happen."""
        mock_msgbox_instance = mock_msgbox_class.return_value
        mock_msgbox_instance.exec.return_value = mock_msgbox_class.StandardButton.No

        controller = GalleryQueueController(mock_main_window)
        controller._add_single_folder(temp_gallery)

        mock_main_window.queue_manager.remove_item.assert_not_called()
        mock_main_window._remove_gallery_from_table.assert_not_called()
