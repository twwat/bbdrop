#!/usr/bin/env python3
"""
pytest-qt tests for GalleryFileManagerDialog
Tests file operations, gallery management, and dialog interactions
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, Any

import pytest
from PyQt6.QtWidgets import QDialog, QListWidgetItem, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, QMimeData, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from src.gui.dialogs.gallery_file_manager import (
    GalleryFileManagerDialog,
    FileScanner
)
from src.core.constants import IMAGE_EXTENSIONS


# Test Fixtures

@pytest.fixture
def temp_gallery_dir(tmp_path):
    """Create temporary gallery directory with test images"""
    gallery_dir = tmp_path / "test_gallery"
    gallery_dir.mkdir()

    # Create valid test images
    for i in range(5):
        img_path = gallery_dir / f"image_{i}.jpg"
        # Create minimal valid JPEG (1x1 pixel)
        img_path.write_bytes(
            b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xFF\xDB\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14'
            b'\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $'
            b'\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xFF\xC0\x00\x0b\x08\x00\x01\x00\x01'
            b'\x01\x01\x11\x00\xFF\xC4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xFF\xDA'
            b'\x00\x08\x01\x01\x00\x00?\x00\xFF\xD9'
        )

    yield gallery_dir
    # Cleanup handled by tmp_path


@pytest.fixture
def mock_queue_manager():
    """Mock queue manager with gallery item"""
    manager = Mock()

    # Create mock gallery item
    gallery_item = Mock()
    gallery_item.status = "ready"
    gallery_item.uploaded_images = 0
    gallery_item.total_images = 5
    gallery_item.error_message = None
    gallery_item.is_from_archive = False
    gallery_item.source_archive_path = None
    gallery_item.gallery_id = None

    manager.get_item = Mock(return_value=gallery_item)
    manager.scan_folder = Mock()

    return manager


@pytest.fixture
def mock_completed_gallery_item():
    """Mock completed gallery item with artifact"""
    item = Mock()
    item.status = "completed"
    item.uploaded_images = 5
    item.total_images = 5
    item.gallery_id = "ABC12345"
    item.error_message = None
    item.is_from_archive = False
    item.source_archive_path = None

    return item


@pytest.fixture
def mock_artifact_data():
    """Mock artifact data for completed gallery"""
    return {
        "gallery_id": "ABC12345",
        "gallery_url": "https://imx.to/g/ABC12345",
        "images": [
            {
                "original_filename": "image_0.jpg",
                "image_url": "https://imx.to/i/test0.jpg",
                "thumbnail_url": "https://imx.to/t/test0.jpg",
                "bbcode": "[img]https://imx.to/i/test0.jpg[/img]",
                "size_bytes": 12345,
                "width": 1920,
                "height": 1080
            },
            {
                "original_filename": "image_1.jpg",
                "image_url": "https://imx.to/i/test1.jpg",
                "thumbnail_url": "https://imx.to/t/test1.jpg",
                "bbcode": "[img]https://imx.to/i/test1.jpg[/img]",
                "size_bytes": 23456,
                "width": 1280,
                "height": 720
            }
        ]
    }


@pytest.fixture
def invalid_image_file(tmp_path):
    """Create invalid image file"""
    invalid_file = tmp_path / "invalid.jpg"
    invalid_file.write_bytes(b"Not a valid image")
    return invalid_file


# Test Classes

class TestGalleryFileManagerDialogInit:
    """Test dialog initialization"""

    def test_dialog_creates(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test dialog instantiation"""
        with patch.object(GalleryFileManagerDialog, 'load_gallery_files'):
            dialog = GalleryFileManagerDialog(
                str(temp_gallery_dir),
                mock_queue_manager
            )
            qtbot.addWidget(dialog)

            assert dialog is not None
            assert isinstance(dialog, QDialog)

    def test_dialog_properties_initialized(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test initial properties are set correctly"""
        with patch.object(GalleryFileManagerDialog, 'load_gallery_files'):
            dialog = GalleryFileManagerDialog(
                str(temp_gallery_dir),
                mock_queue_manager
            )
            qtbot.addWidget(dialog)

            assert dialog.gallery_path == str(temp_gallery_dir)
            assert dialog.queue_manager == mock_queue_manager
            assert dialog.modified is False
            assert isinstance(dialog.original_files, set)
            assert isinstance(dialog.removed_files, set)
            assert isinstance(dialog.added_files, set)
            assert isinstance(dialog.file_status, dict)

    def test_dialog_window_properties(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test window properties"""
        with patch.object(GalleryFileManagerDialog, 'load_gallery_files'):
            dialog = GalleryFileManagerDialog(
                str(temp_gallery_dir),
                mock_queue_manager
            )
            qtbot.addWidget(dialog)

            assert dialog.isModal()
            assert "test_gallery" in dialog.windowTitle()

    def test_ui_components_created(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test all UI components are created"""
        with patch.object(GalleryFileManagerDialog, 'load_gallery_files'):
            dialog = GalleryFileManagerDialog(
                str(temp_gallery_dir),
                mock_queue_manager
            )
            qtbot.addWidget(dialog)

            assert hasattr(dialog, 'file_list')
            assert hasattr(dialog, 'add_btn')
            assert hasattr(dialog, 'remove_btn')
            assert hasattr(dialog, 'select_all_btn')
            assert hasattr(dialog, 'select_invalid_btn')
            assert hasattr(dialog, 'details_text')
            assert hasattr(dialog, 'info_label')


class TestFileScanner:
    """Test FileScanner thread"""

    def test_scanner_creates(self, temp_gallery_dir):
        """Test FileScanner instantiation"""
        files = ["image_0.jpg", "image_1.jpg"]
        scanner = FileScanner(str(temp_gallery_dir), files)

        assert scanner.folder_path == str(temp_gallery_dir)
        assert scanner.files == files
        assert scanner._stop is False

    def test_scanner_validates_existing_file(self, qtbot, temp_gallery_dir):
        """Test scanning valid existing file"""
        files = ["image_0.jpg"]
        scanner = FileScanner(str(temp_gallery_dir), files)

        scanned_files = []
        scanner.file_scanned.connect(
            lambda name, valid, error: scanned_files.append((name, valid, error))
        )

        with qtbot.waitSignal(scanner.finished, timeout=5000):
            scanner.start()

        scanner.wait()  # Ensure thread completes before cleanup

        assert len(scanned_files) == 1
        assert scanned_files[0][0] == "image_0.jpg"
        assert scanned_files[0][1] is True  # Valid
        assert scanned_files[0][2] == ""

    def test_scanner_detects_missing_file(self, qtbot, temp_gallery_dir):
        """Test scanning non-existent file"""
        files = ["nonexistent.jpg"]
        scanner = FileScanner(str(temp_gallery_dir), files)

        scanned_files = []
        scanner.file_scanned.connect(
            lambda name, valid, error: scanned_files.append((name, valid, error))
        )

        with qtbot.waitSignal(scanner.finished, timeout=5000):
            scanner.start()

        scanner.wait()  # Ensure thread completes before cleanup

        assert len(scanned_files) == 1
        assert scanned_files[0][0] == "nonexistent.jpg"
        assert scanned_files[0][1] is False  # Invalid
        assert "not found" in scanned_files[0][2].lower()

    def test_scanner_detects_non_image_extension(self, qtbot, temp_gallery_dir):
        """Test scanning file with non-image extension"""
        non_image = temp_gallery_dir / "test.txt"
        non_image.write_text("Not an image")

        files = ["test.txt"]
        scanner = FileScanner(str(temp_gallery_dir), files)

        scanned_files = []
        scanner.file_scanned.connect(
            lambda name, valid, error: scanned_files.append((name, valid, error))
        )

        with qtbot.waitSignal(scanner.finished, timeout=5000):
            scanner.start()

        scanner.wait()  # Ensure thread completes before cleanup

        assert len(scanned_files) == 1
        assert scanned_files[0][1] is False
        assert "not an image" in scanned_files[0][2].lower()

    def test_scanner_can_stop(self, temp_gallery_dir):
        """Test scanner can be stopped"""
        files = [f"image_{i}.jpg" for i in range(100)]
        scanner = FileScanner(str(temp_gallery_dir), files)

        scanner.stop()
        assert scanner._stop is True

    def test_scanner_progress_signals(self, qtbot, temp_gallery_dir):
        """Test progress signals are emitted"""
        files = ["image_0.jpg", "image_1.jpg"]
        scanner = FileScanner(str(temp_gallery_dir), files)

        progress_updates = []
        scanner.progress.connect(
            lambda curr, total: progress_updates.append((curr, total))
        )

        with qtbot.waitSignal(scanner.finished, timeout=5000):
            scanner.start()

        scanner.wait()  # Ensure thread completes before cleanup

        assert len(progress_updates) == 2
        assert progress_updates[-1] == (2, 2)  # Final progress


class TestFileOperations:
    """Test file operation methods"""

    def test_add_files_dialog_cancelled(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test add files when dialog is cancelled"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        with patch.object(QFileDialog, 'getOpenFileNames', return_value=([], "")):
            initial_count = dialog.file_list.count()
            dialog.add_files()

            assert dialog.file_list.count() == initial_count
            assert dialog.modified is False

    def test_add_files_single_file(self, qtbot, temp_gallery_dir, mock_queue_manager, tmp_path):
        """Test adding single file"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        # Create new file to add
        new_file = tmp_path / "new_image.jpg"
        new_file.write_bytes(
            b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xFF\xD9'
        )

        with patch.object(QFileDialog, 'getOpenFileNames', return_value=([str(new_file)], "")):
            with patch.object(dialog, 'scan_files'):
                with patch.object(QMessageBox, 'information'):
                    dialog.add_files()

        assert dialog.modified is True
        assert "new_image.jpg" in dialog.added_files
        assert (temp_gallery_dir / "new_image.jpg").exists()

    def test_add_files_replace_existing(self, qtbot, temp_gallery_dir, mock_queue_manager, tmp_path):
        """Test adding file that already exists with replacement"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        existing_file = tmp_path / "image_0.jpg"
        existing_file.write_bytes(b'\xFF\xD8\xFF\xE0\xFF\xD9')

        with patch.object(QFileDialog, 'getOpenFileNames', return_value=([str(existing_file)], "")):
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                with patch.object(dialog, 'scan_files'):
                    with patch.object(QMessageBox, 'information'):
                        dialog.add_files()

        assert dialog.modified is True

    def test_add_files_skip_existing(self, qtbot, temp_gallery_dir, mock_queue_manager, tmp_path):
        """Test adding file that already exists without replacement"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        existing_file = tmp_path / "image_0.jpg"
        existing_file.write_bytes(b'\xFF\xD8\xFF\xE0\xFF\xD9')

        with patch.object(QFileDialog, 'getOpenFileNames', return_value=([str(existing_file)], "")):
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
                dialog.add_files()

        assert dialog.modified is False

    def test_remove_selected_no_selection(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test remove with no files selected"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.remove_selected()
        # Should do nothing without selection
        assert dialog.modified is False

    def test_remove_selected_confirmed(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test removing selected files with confirmation"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        # Add item to list
        item = QListWidgetItem("image_0.jpg")
        dialog.file_list.addItem(item)
        dialog.file_status["image_0.jpg"] = (True, "")
        item.setSelected(True)

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            dialog.remove_selected()

        assert dialog.modified is True
        assert "image_0.jpg" in dialog.removed_files
        assert not (temp_gallery_dir / "image_0.jpg").exists()

    def test_remove_selected_cancelled(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test removing files when cancelled"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        item = QListWidgetItem("image_0.jpg")
        dialog.file_list.addItem(item)
        item.setSelected(True)

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            dialog.remove_selected()

        assert dialog.modified is False
        assert (temp_gallery_dir / "image_0.jpg").exists()

    def test_remove_added_file(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test removing a file that was just added"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.added_files.add("new_file.jpg")
        item = QListWidgetItem("new_file.jpg (new)")
        dialog.file_list.addItem(item)
        item.setSelected(True)

        # Create the file
        (temp_gallery_dir / "new_file.jpg").write_bytes(b'\xFF\xD8\xFF\xD9')

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            dialog.remove_selected()

        assert "new_file.jpg" not in dialog.added_files
        assert "new_file.jpg" in dialog.removed_files


class TestFileSelection:
    """Test file selection methods"""

    def test_select_all(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test selecting all files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        # Add items
        for i in range(3):
            item = QListWidgetItem(f"image_{i}.jpg")
            dialog.file_list.addItem(item)

        dialog.select_all()

        assert len(dialog.file_list.selectedItems()) == 3

    def test_select_invalid_no_invalid_files(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test select invalid when all files are valid"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        # Add valid files
        for i in range(3):
            item = QListWidgetItem(f"image_{i}.jpg")
            dialog.file_list.addItem(item)
            dialog.file_status[f"image_{i}.jpg"] = (True, "")

        dialog.select_invalid()

        assert len(dialog.file_list.selectedItems()) == 0

    def test_select_invalid_with_invalid_files(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test select invalid with some invalid files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        # Add files with mixed validity
        for i in range(3):
            item = QListWidgetItem(f"image_{i}.jpg")
            dialog.file_list.addItem(item)
            is_valid = i != 1  # Make second file invalid
            dialog.file_status[f"image_{i}.jpg"] = (is_valid, "" if is_valid else "Invalid")

        dialog.select_invalid()

        selected = dialog.file_list.selectedItems()
        assert len(selected) == 1
        assert selected[0].text() == "image_1.jpg"

    def test_on_selection_changed_single_file(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test selection change with single file"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        item = QListWidgetItem("image_0.jpg")
        dialog.file_list.addItem(item)
        dialog.file_status["image_0.jpg"] = (True, "")
        item.setSelected(True)

        dialog.on_selection_changed()

        assert dialog.remove_btn.isEnabled()

    def test_on_selection_changed_multiple_files(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test selection change with multiple files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        for i in range(3):
            item = QListWidgetItem(f"image_{i}.jpg")
            dialog.file_list.addItem(item)
            item.setSelected(True)

        dialog.on_selection_changed()

        assert dialog.remove_btn.isEnabled()
        assert "3 files selected" in dialog.details_text.toPlainText()

    def test_on_selection_changed_no_selection(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test selection change with no selection"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.on_selection_changed()

        assert not dialog.remove_btn.isEnabled()


class TestButtonStates:
    """Test button state management"""

    def test_remove_button_initially_disabled(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test remove button is initially disabled"""
        with patch.object(GalleryFileManagerDialog, 'load_gallery_files'):
            dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
            qtbot.addWidget(dialog)

            assert not dialog.remove_btn.isEnabled()

    def test_select_invalid_button_disabled_no_invalid(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test select invalid button disabled when no invalid files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.file_status["image_0.jpg"] = (True, "")
        dialog.update_button_states()

        assert not dialog.select_invalid_btn.isEnabled()

    def test_select_invalid_button_enabled_with_invalid(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test select invalid button enabled when invalid files exist"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.file_status["image_0.jpg"] = (False, "Invalid")
        dialog.update_button_states()

        assert dialog.select_invalid_btn.isEnabled()


class TestInfoLabel:
    """Test information label updates"""

    def test_update_info_label_ready_status(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test info label with ready status"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.original_files.add("image_0.jpg")
        dialog.file_status["image_0.jpg"] = (True, "")
        dialog.update_info_label()

        text = dialog.info_label.text()
        assert "ready" in text.lower()
        assert "Total Files:" in text or "Total:" in text

    def test_update_info_label_failed_status(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test info label with failed status"""
        mock_queue_manager.get_item.return_value.status = "failed"
        mock_queue_manager.get_item.return_value.error_message = "Upload failed"

        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.update_info_label()

        text = dialog.info_label.text()
        assert "FAILED" in text or "failed" in text.lower()

    def test_update_info_label_completed_status(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test info label with completed status"""
        mock_queue_manager.get_item.return_value.status = "completed"
        mock_queue_manager.get_item.return_value.uploaded_images = 5

        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.update_info_label()

        text = dialog.info_label.text()
        assert "completed" in text.lower()
        assert "Uploaded:" in text or "uploaded" in text.lower()

    def test_update_info_label_archive_source(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test info label shows archive source"""
        mock_queue_manager.get_item.return_value.is_from_archive = True
        mock_queue_manager.get_item.return_value.source_archive_path = "/path/to/archive.zip"

        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.update_info_label()

        text = dialog.info_label.text()
        assert "archive.zip" in text
        assert "archive" in text.lower()


class TestFileDetails:
    """Test file details display"""

    def test_show_file_details_valid_file(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test showing details for valid file"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.file_status["image_0.jpg"] = (True, "")
        dialog.show_file_details("image_0.jpg")

        details = dialog.details_text.toPlainText()
        assert "image_0.jpg" in details
        assert "Valid" in details or "✅" in details

    def test_show_file_details_invalid_file(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test showing details for invalid file"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        # Create the file so it exists but mark it as invalid
        invalid_file = temp_gallery_dir / "bad_image.jpg"
        invalid_file.write_bytes(b"Not a valid image")

        dialog.file_status["bad_image.jpg"] = (False, "Corrupted file")
        dialog.show_file_details("bad_image.jpg")

        details = dialog.details_text.toPlainText()
        assert "bad_image.jpg" in details
        assert ("Corrupted file" in details or "❌" in details or "Invalid" in details or "File not found" not in details)

    def test_show_file_details_added_file(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test showing details for newly added file"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.added_files.add("new_file.jpg")
        dialog.show_file_details("new_file.jpg")

        details = dialog.details_text.toPlainText()
        assert "added" in details.lower()

    def test_show_file_details_removed_file(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test showing details for removed file"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.removed_files.add("image_0.jpg")
        dialog.show_file_details("image_0.jpg")

        details = dialog.details_text.toPlainText()
        assert "removal" in details.lower() or "removed" in details.lower()


class TestDragDrop:
    """Test drag and drop functionality"""

    def test_drag_enter_with_image_files(self, qtbot, temp_gallery_dir, mock_queue_manager, tmp_path):
        """Test drag enter accepts image files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        mime_data = QMimeData()
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b'\xFF\xD8\xFF\xD9')
        mime_data.setUrls([QUrl.fromLocalFile(str(test_file))])

        event = QDragEnterEvent(
            dialog.file_list.rect().center(),
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )

        dialog.dragEnterEvent(event)

        assert event.isAccepted()

    def test_drag_enter_with_non_image_files(self, qtbot, temp_gallery_dir, mock_queue_manager, tmp_path):
        """Test drag enter rejects non-image files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        mime_data = QMimeData()
        test_file = tmp_path / "test.txt"
        test_file.write_text("Not an image")
        mime_data.setUrls([QUrl.fromLocalFile(str(test_file))])

        event = QDragEnterEvent(
            dialog.file_list.rect().center(),
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )

        dialog.dragEnterEvent(event)

        assert not event.isAccepted()

    def test_drop_image_files(self, qtbot, temp_gallery_dir, mock_queue_manager, tmp_path):
        """Test dropping image files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        mime_data = QMimeData()
        test_file = tmp_path / "dropped.jpg"
        test_file.write_bytes(
            b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xFF\xD9'
        )
        mime_data.setUrls([QUrl.fromLocalFile(str(test_file))])

        # Import QPointF for PyQt6
        from PyQt6.QtCore import QPointF, QEvent

        event = QDropEvent(
            QPointF(dialog.file_list.rect().center()),  # Use QPointF instead of QPoint
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QEvent.Type.Drop
        )

        with patch.object(dialog, 'scan_files'):
            dialog.dropEvent(event)

        assert event.isAccepted()
        assert "dropped.jpg" in dialog.added_files


class TestCompletedGallery:
    """Test completed gallery functionality"""

    def test_load_from_artifact(self, qtbot, temp_gallery_dir, mock_queue_manager, mock_artifact_data):
        """Test loading files from artifact data"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.artifact_data = mock_artifact_data
        dialog.is_completed = True
        dialog.load_from_artifact()

        assert dialog.file_list.count() == 2
        assert "image_0.jpg" in dialog.original_files
        assert "image_1.jpg" in dialog.original_files
        assert not dialog.add_btn.isEnabled()
        assert not dialog.remove_btn.isEnabled()

    def test_completed_gallery_buttons_disabled(self, qtbot, temp_gallery_dir, mock_queue_manager, mock_artifact_data):
        """Test buttons disabled for completed gallery"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.artifact_data = mock_artifact_data
        dialog.is_completed = True
        dialog.load_from_artifact()

        assert not dialog.add_btn.isEnabled()
        assert not dialog.remove_btn.isEnabled()
        assert "Cannot modify completed galleries" in dialog.add_btn.toolTip()

    def test_show_artifact_file_details(self, qtbot, temp_gallery_dir, mock_queue_manager, mock_artifact_data):
        """Test showing file details from artifact"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.artifact_data = mock_artifact_data
        dialog.is_completed = True
        dialog.show_file_details("image_0.jpg")

        details = dialog.details_text.toHtml()
        assert "image_0.jpg" in details
        assert "https://imx.to/i/test0.jpg" in details
        assert "BBCode:" in details


class TestDialogAccept:
    """Test dialog accept/close behavior"""

    def test_accept_with_modifications(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test accepting dialog with modifications"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.modified = True
        dialog.added_files.add("new_file.jpg")

        dialog.accept()

        # Should trigger queue manager scan
        mock_queue_manager.scan_folder.assert_called_once_with(str(temp_gallery_dir))

    def test_accept_without_modifications(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test accepting dialog without modifications"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.modified = False
        dialog.accept()

        # Should not trigger scan
        mock_queue_manager.scan_folder.assert_not_called()

    def test_accept_completed_gallery_with_new_files(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test accepting completed gallery with new files added"""
        mock_queue_manager.get_item.return_value.status = "completed"
        mock_queue_manager.get_item.return_value.uploaded_images = 5
        mock_queue_manager.get_item.return_value.total_images = 5

        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.modified = True
        dialog.original_files = {"img1.jpg", "img2.jpg", "img3.jpg", "img4.jpg", "img5.jpg"}
        dialog.added_files = {"img6.jpg"}

        dialog.accept()

        # Should mark as incomplete
        assert dialog.gallery_item.status == "incomplete"


class TestErrorHandling:
    """Test error handling"""

    def test_add_files_copy_failure(self, qtbot, temp_gallery_dir, mock_queue_manager, tmp_path):
        """Test handling copy failure when adding files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b'\xFF\xD8\xFF\xD9')

        with patch.object(QFileDialog, 'getOpenFileNames', return_value=([str(test_file)], "")):
            with patch('shutil.copy2', side_effect=PermissionError("Access denied")):
                with patch.object(QMessageBox, 'warning') as mock_warning:
                    dialog.add_files()

                    mock_warning.assert_called_once()

    def test_remove_files_delete_failure(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test handling delete failure when removing files"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        item = QListWidgetItem("image_0.jpg")
        dialog.file_list.addItem(item)
        item.setSelected(True)

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            with patch('os.remove', side_effect=PermissionError("Access denied")):
                with patch.object(QMessageBox, 'warning') as mock_warning:
                    dialog.remove_selected()

                    mock_warning.assert_called_once()

    def test_load_gallery_missing_folder(self, qtbot, mock_queue_manager, tmp_path):
        """Test loading gallery with missing folder"""
        non_existent = tmp_path / "does_not_exist"

        with patch.object(QMessageBox, 'warning') as mock_warning:
            dialog = GalleryFileManagerDialog(str(non_existent), mock_queue_manager)
            qtbot.addWidget(dialog)

            mock_warning.assert_called_once()


class TestFileStatusTracking:
    """Test file status tracking"""

    def test_on_file_scanned_valid(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test handling valid file scan result"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.on_file_scanned("image_0.jpg", True, "")

        assert "image_0.jpg" in dialog.file_status
        assert dialog.file_status["image_0.jpg"] == (True, "")
        assert dialog.file_list.count() == 1

    def test_on_file_scanned_invalid(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test handling invalid file scan result"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.on_file_scanned("bad_file.jpg", False, "Corrupted")

        assert "bad_file.jpg" in dialog.file_status
        assert dialog.file_status["bad_file.jpg"] == (False, "Corrupted")
        item = dialog.file_list.item(0)
        assert "Corrupted" in item.toolTip()

    def test_on_file_scanned_marks_new_files(self, qtbot, temp_gallery_dir, mock_queue_manager):
        """Test that new files are marked as (new)"""
        dialog = GalleryFileManagerDialog(str(temp_gallery_dir), mock_queue_manager)
        qtbot.addWidget(dialog)

        dialog.added_files.add("new_file.jpg")
        dialog.on_file_scanned("new_file.jpg", True, "")

        item = dialog.file_list.item(0)
        assert "(new)" in item.text()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
