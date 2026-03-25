#!/usr/bin/env python3
"""
Unit tests for media type detection wiring in GalleryQueueController.

Tests that _resolve_media_type correctly detects media types, shows the
MixedMediaDialog for mixed content, respects QSettings remembered choices,
and that the add methods propagate media_type to queue items.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call

from PyQt6.QtCore import QMutex

from src.gui.gallery_queue_controller import GalleryQueueController
from src.storage.queue_manager import GalleryQueueItem


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_main_window():
    """Create a mock main window with attributes needed by the queue controller."""
    mw = Mock()
    mw.queue_manager = Mock()
    mw.queue_manager.mutex = QMutex()
    mw.queue_manager.items = {}
    mw.queue_manager.store = Mock()
    mw.gallery_table = Mock()
    mw.gallery_table.current_tab = "Main"
    mw.template_combo = Mock()
    mw.template_combo.currentText.return_value = "default"
    mw._get_default_host = Mock(return_value="imx")
    mw._check_if_gallery_exists = Mock(return_value=[])
    mw._add_gallery_to_table = Mock()
    return mw


@pytest.fixture
def controller(mock_main_window):
    """Create a GalleryQueueController with a mocked main window."""
    return GalleryQueueController(mock_main_window)


# =========================================================================
# _resolve_media_type
# =========================================================================


class TestResolveMediaType:
    """Tests for _resolve_media_type method."""

    def test_image_folder_returns_image(self, controller, mock_main_window):
        """Detect an images-only folder and return 'image' without dialog."""
        mock_main_window.queue_manager._detect_media_type.return_value = "image"

        result = controller._resolve_media_type("/test/images_only")

        assert result == "image"

    def test_video_folder_returns_video(self, controller, mock_main_window):
        """Detect a videos-only folder and return 'video' without dialog."""
        mock_main_window.queue_manager._detect_media_type.return_value = "video"

        result = controller._resolve_media_type("/test/videos_only")

        assert result == "video"

    def test_single_video_file_returns_video(self, controller, mock_main_window):
        """Detect a single video file path and return 'video'."""
        mock_main_window.queue_manager._detect_media_type.return_value = "video"

        result = controller._resolve_media_type("/test/clip.mp4")

        assert result == "video"

    @patch("src.gui.gallery_queue_controller.QSettings")
    def test_mixed_with_remembered_exclude_returns_video(
        self, mock_settings_cls, controller, mock_main_window
    ):
        """When mixed is detected and the user previously chose 'exclude',
        return 'video' without showing a dialog."""
        mock_main_window.queue_manager._detect_media_type.return_value = "mixed"

        settings_instance = MagicMock()
        mock_settings_cls.return_value = settings_instance
        settings_instance.value.side_effect = lambda key, default=None, type=None: {
            "Video/remember_mixed_choice": True,
            "Video/mixed_choice": "exclude",
        }.get(key, default)

        result = controller._resolve_media_type("/test/mixed_folder")

        assert result == "video"

    @patch("src.gui.gallery_queue_controller.QSettings")
    def test_mixed_with_remembered_include_returns_mixed(
        self, mock_settings_cls, controller, mock_main_window
    ):
        """When mixed is detected and the user previously chose 'include',
        return 'mixed' without showing a dialog."""
        mock_main_window.queue_manager._detect_media_type.return_value = "mixed"

        settings_instance = MagicMock()
        mock_settings_cls.return_value = settings_instance
        settings_instance.value.side_effect = lambda key, default=None, type=None: {
            "Video/remember_mixed_choice": True,
            "Video/mixed_choice": "include",
        }.get(key, default)

        result = controller._resolve_media_type("/test/mixed_folder")

        assert result == "mixed"

    @patch("src.gui.dialogs.mixed_media_dialog.MixedMediaDialog")
    @patch("src.gui.gallery_queue_controller.QSettings")
    def test_mixed_shows_dialog_when_not_remembered(
        self, mock_settings_cls, mock_dialog_cls, controller, mock_main_window
    ):
        """When mixed is detected and no remembered choice, show the dialog."""
        mock_main_window.queue_manager._detect_media_type.return_value = "mixed"
        mock_main_window.queue_manager._get_image_files.return_value = ["a.jpg", "b.png"]
        mock_main_window.queue_manager._get_video_files.return_value = ["c.mp4"]

        settings_instance = MagicMock()
        mock_settings_cls.return_value = settings_instance
        settings_instance.value.side_effect = lambda key, default=None, type=None: {
            "Video/remember_mixed_choice": False,
            "Video/mixed_choice": "exclude",
        }.get(key, default)

        dialog_instance = MagicMock()
        mock_dialog_cls.return_value = dialog_instance
        mock_dialog_cls.DialogCode.Accepted = 1
        mock_dialog_cls.INCLUDE_IMAGES = "include"
        mock_dialog_cls.EXCLUDE_IMAGES = "exclude"
        dialog_instance.exec.return_value = 1  # Accepted
        dialog_instance.result_choice = "exclude"
        dialog_instance.should_remember = False

        result = controller._resolve_media_type("/test/mixed_folder")

        mock_dialog_cls.assert_called_once_with(
            folder_name="mixed_folder",
            image_count=2,
            video_count=1,
            parent=mock_main_window,
        )
        dialog_instance.exec.assert_called_once()
        assert result == "video"

    @patch("src.gui.dialogs.mixed_media_dialog.MixedMediaDialog")
    @patch("src.gui.gallery_queue_controller.QSettings")
    def test_mixed_dialog_include_returns_mixed(
        self, mock_settings_cls, mock_dialog_cls, controller, mock_main_window
    ):
        """When user clicks 'include' in the dialog, return 'mixed'."""
        mock_main_window.queue_manager._detect_media_type.return_value = "mixed"
        mock_main_window.queue_manager._get_image_files.return_value = ["a.jpg"]
        mock_main_window.queue_manager._get_video_files.return_value = ["b.mp4"]

        settings_instance = MagicMock()
        mock_settings_cls.return_value = settings_instance
        settings_instance.value.side_effect = lambda key, default=None, type=None: {
            "Video/remember_mixed_choice": False,
        }.get(key, default)

        dialog_instance = MagicMock()
        mock_dialog_cls.return_value = dialog_instance
        mock_dialog_cls.DialogCode.Accepted = 1
        mock_dialog_cls.INCLUDE_IMAGES = "include"
        mock_dialog_cls.EXCLUDE_IMAGES = "exclude"
        dialog_instance.exec.return_value = 1
        dialog_instance.result_choice = "include"
        dialog_instance.should_remember = False

        result = controller._resolve_media_type("/test/mixed_folder")

        assert result == "mixed"

    @patch("src.gui.dialogs.mixed_media_dialog.MixedMediaDialog")
    @patch("src.gui.gallery_queue_controller.QSettings")
    def test_mixed_dialog_remember_saves_to_settings(
        self, mock_settings_cls, mock_dialog_cls, controller, mock_main_window
    ):
        """When user checks 'remember', the choice is saved to QSettings."""
        mock_main_window.queue_manager._detect_media_type.return_value = "mixed"
        mock_main_window.queue_manager._get_image_files.return_value = ["a.jpg"]
        mock_main_window.queue_manager._get_video_files.return_value = ["b.mp4"]

        settings_instance = MagicMock()
        mock_settings_cls.return_value = settings_instance
        settings_instance.value.side_effect = lambda key, default=None, type=None: {
            "Video/remember_mixed_choice": False,
        }.get(key, default)

        dialog_instance = MagicMock()
        mock_dialog_cls.return_value = dialog_instance
        mock_dialog_cls.DialogCode.Accepted = 1
        mock_dialog_cls.INCLUDE_IMAGES = "include"
        mock_dialog_cls.EXCLUDE_IMAGES = "exclude"
        dialog_instance.exec.return_value = 1
        dialog_instance.result_choice = "include"
        dialog_instance.should_remember = True

        controller._resolve_media_type("/test/mixed_folder")

        settings_instance.setValue.assert_any_call("Video/remember_mixed_choice", True)
        settings_instance.setValue.assert_any_call("Video/mixed_choice", "include")

    @patch("src.gui.dialogs.mixed_media_dialog.MixedMediaDialog")
    @patch("src.gui.gallery_queue_controller.QSettings")
    def test_mixed_dialog_rejected_defaults_to_video(
        self, mock_settings_cls, mock_dialog_cls, controller, mock_main_window
    ):
        """When user closes the dialog without choosing, default to 'video'."""
        mock_main_window.queue_manager._detect_media_type.return_value = "mixed"
        mock_main_window.queue_manager._get_image_files.return_value = ["a.jpg"]
        mock_main_window.queue_manager._get_video_files.return_value = ["b.mp4"]

        settings_instance = MagicMock()
        mock_settings_cls.return_value = settings_instance
        settings_instance.value.side_effect = lambda key, default=None, type=None: {
            "Video/remember_mixed_choice": False,
        }.get(key, default)

        dialog_instance = MagicMock()
        mock_dialog_cls.return_value = dialog_instance
        mock_dialog_cls.DialogCode.Accepted = 1
        mock_dialog_cls.EXCLUDE_IMAGES = "exclude"
        dialog_instance.exec.return_value = 0  # Rejected

        result = controller._resolve_media_type("/test/mixed_folder")

        assert result == "video"


# =========================================================================
# _apply_media_type
# =========================================================================


class TestApplyMediaType:
    """Tests for _apply_media_type method."""

    def test_sets_media_type_and_saves(self, controller, mock_main_window):
        """Verify media_type is set on the item and persisted."""
        item = GalleryQueueItem(path="/test/gallery")
        item.media_type = "image"
        mock_main_window.queue_manager.get_item.return_value = item

        with patch("src.gui.gallery_queue_controller.log"):
            controller._apply_media_type("/test/gallery", "video")

        assert item.media_type == "video"
        mock_main_window.queue_manager._save_single_item.assert_called_once_with(item)

    def test_skips_save_when_unchanged(self, controller, mock_main_window):
        """Verify no save happens when media_type is already correct."""
        item = GalleryQueueItem(path="/test/gallery")
        item.media_type = "video"
        mock_main_window.queue_manager.get_item.return_value = item

        with patch("src.gui.gallery_queue_controller.log"):
            controller._apply_media_type("/test/gallery", "video")

        mock_main_window.queue_manager._save_single_item.assert_not_called()

    def test_handles_missing_item(self, controller, mock_main_window):
        """Verify no error when item is not found in queue."""
        mock_main_window.queue_manager.get_item.return_value = None

        with patch("src.gui.gallery_queue_controller.log"):
            controller._apply_media_type("/test/nonexistent", "video")

        mock_main_window.queue_manager._save_single_item.assert_not_called()


# =========================================================================
# Integration: _add_single_folder sets media_type
# =========================================================================


class TestAddSingleFolderMediaType:
    """Tests that _add_single_folder wires media type detection."""

    def test_video_folder_gets_video_media_type(self, controller, mock_main_window):
        """Add a videos-only folder and verify media_type is set to 'video'."""
        mock_main_window.queue_manager.get_item.side_effect = [
            None,  # first call: duplicate check returns None (not in queue)
            GalleryQueueItem(path="/test/videos", media_type="image"),  # _apply_media_type
            GalleryQueueItem(path="/test/videos", media_type="video"),  # _add_gallery_to_table
        ]
        mock_main_window.queue_manager._detect_media_type.return_value = "video"
        mock_main_window.queue_manager.add_item.return_value = True

        with patch("src.gui.gallery_queue_controller.log"), \
             patch("src.gui.gallery_queue_controller.QTimer"):
            controller._add_single_folder("/test/videos")

        mock_main_window.queue_manager._detect_media_type.assert_called_once_with("/test/videos")
        mock_main_window.queue_manager._save_single_item.assert_called_once()
        saved_item = mock_main_window.queue_manager._save_single_item.call_args[0][0]
        assert saved_item.media_type == "video"

    def test_image_folder_keeps_default_media_type(self, controller, mock_main_window):
        """Add an images-only folder and verify media_type stays 'image' (no save needed)."""
        item = GalleryQueueItem(path="/test/images", media_type="image")
        mock_main_window.queue_manager.get_item.side_effect = [
            None,  # duplicate check
            item,  # _apply_media_type (media_type already "image", skip save)
            item,  # _add_gallery_to_table
        ]
        mock_main_window.queue_manager._detect_media_type.return_value = "image"
        mock_main_window.queue_manager.add_item.return_value = True

        with patch("src.gui.gallery_queue_controller.log"), \
             patch("src.gui.gallery_queue_controller.QTimer"):
            controller._add_single_folder("/test/images")

        mock_main_window.queue_manager._detect_media_type.assert_called_once_with("/test/images")
        # No save needed since media_type == "image" (the default)
        mock_main_window.queue_manager._save_single_item.assert_not_called()

    @patch("src.gui.dialogs.mixed_media_dialog.MixedMediaDialog")
    @patch("src.gui.gallery_queue_controller.QSettings")
    def test_mixed_folder_shows_dialog(
        self, mock_settings_cls, mock_dialog_cls, controller, mock_main_window
    ):
        """Add a mixed-content folder and verify the dialog is shown."""
        mock_main_window.queue_manager._detect_media_type.return_value = "mixed"
        mock_main_window.queue_manager._get_image_files.return_value = ["a.jpg"]
        mock_main_window.queue_manager._get_video_files.return_value = ["b.mp4"]

        settings_instance = MagicMock()
        mock_settings_cls.return_value = settings_instance
        settings_instance.value.side_effect = lambda key, default=None, type=None: {
            "Video/remember_mixed_choice": False,
        }.get(key, default)

        dialog_instance = MagicMock()
        mock_dialog_cls.return_value = dialog_instance
        mock_dialog_cls.DialogCode.Accepted = 1
        mock_dialog_cls.INCLUDE_IMAGES = "include"
        mock_dialog_cls.EXCLUDE_IMAGES = "exclude"
        dialog_instance.exec.return_value = 1
        dialog_instance.result_choice = "exclude"
        dialog_instance.should_remember = False

        item = GalleryQueueItem(path="/test/mixed", media_type="image")
        mock_main_window.queue_manager.get_item.side_effect = [
            None,  # duplicate check
            item,  # _apply_media_type
            item,  # _add_gallery_to_table
        ]
        mock_main_window.queue_manager.add_item.return_value = True

        with patch("src.gui.gallery_queue_controller.log"), \
             patch("src.gui.gallery_queue_controller.QTimer"):
            controller._add_single_folder("/test/mixed")

        mock_dialog_cls.assert_called_once()
        dialog_instance.exec.assert_called_once()


# =========================================================================
# Integration: _add_archive_folder sets media_type
# =========================================================================


class TestAddArchiveFolderMediaType:
    """Tests that _add_archive_folder wires media type detection."""

    def test_archive_video_folder_gets_video_media_type(self, controller, mock_main_window):
        """Add an archive-extracted video folder and verify media_type='video'."""
        mock_main_window.queue_manager._detect_media_type.return_value = "video"
        mock_main_window.queue_manager.add_item.return_value = True

        item = GalleryQueueItem(path="/tmp/extract_myvids", media_type="image")
        mock_main_window.queue_manager.get_item.side_effect = [
            item,  # _apply_media_type
            item,  # inside if-result block
        ]

        with patch("src.gui.gallery_queue_controller.log"):
            controller._add_archive_folder("/tmp/extract_myvids", "/orig/archive.zip")

        mock_main_window.queue_manager._detect_media_type.assert_called_once_with(
            "/tmp/extract_myvids"
        )
        mock_main_window.queue_manager._save_single_item.assert_called_once_with(item)
        assert item.media_type == "video"


# =========================================================================
# Integration: _add_multiple_folders_with_duplicate_detection sets media_type
# =========================================================================


class TestAddMultipleFoldersMediaType:
    """Tests that _add_multiple_folders_with_duplicate_detection wires media type detection."""

    @patch("src.gui.gallery_queue_controller.QTimer")
    def test_multiple_folders_each_get_media_type(
        self, mock_timer, controller, mock_main_window
    ):
        """Each folder in a multi-add batch gets its own media type detection."""
        mock_main_window.queue_manager._detect_media_type.side_effect = ["image", "video"]
        mock_main_window.queue_manager.add_item.return_value = True

        item_images = GalleryQueueItem(path="/test/images", media_type="image")
        item_videos = GalleryQueueItem(path="/test/videos", media_type="image")

        # get_item is called once per _apply_media_type and once per _add_gallery_to_table
        mock_main_window.queue_manager.get_item.side_effect = [
            item_images,  # _apply_media_type for /test/images (media_type already image, skip save)
            item_images,  # _add_gallery_to_table
            item_videos,  # _apply_media_type for /test/videos
            item_videos,  # _add_gallery_to_table
        ]

        with patch("src.gui.gallery_queue_controller.log"), \
             patch(
                 "src.gui.dialogs.duplicate_detection_dialogs.show_duplicate_detection_dialogs",
                 return_value=(["/test/images", "/test/videos"], []),
             ):
            controller._add_multiple_folders_with_duplicate_detection(
                ["/test/images", "/test/videos"]
            )

        assert mock_main_window.queue_manager._detect_media_type.call_count == 2
        assert item_videos.media_type == "video"
        # images folder stays "image" so no save triggered by _apply_media_type
        # videos folder changed from "image" to "video" so save triggered
        mock_main_window.queue_manager._save_single_item.assert_called_once_with(item_videos)

    @patch("src.gui.gallery_queue_controller.QTimer")
    def test_replace_folders_get_media_type(
        self, mock_timer, controller, mock_main_window
    ):
        """Folders going through the replacement path also get media type detection."""
        mock_main_window.queue_manager._detect_media_type.return_value = "video"
        mock_main_window.queue_manager.add_item.return_value = True

        item = GalleryQueueItem(path="/test/replaced", media_type="image")
        mock_main_window.queue_manager.get_item.side_effect = [
            item,  # _apply_media_type
            item,  # _add_gallery_to_table
        ]

        with patch("src.gui.gallery_queue_controller.log"), \
             patch(
                 "src.gui.dialogs.duplicate_detection_dialogs.show_duplicate_detection_dialogs",
                 return_value=([], ["/test/replaced"]),
             ):
            controller._add_multiple_folders_with_duplicate_detection(["/test/replaced"])

        mock_main_window.queue_manager._detect_media_type.assert_called_once_with("/test/replaced")
        assert item.media_type == "video"
