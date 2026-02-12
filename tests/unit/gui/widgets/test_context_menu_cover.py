"""Tests for cover photo context menu actions."""
import pytest
from unittest.mock import patch, MagicMock, Mock


class TestCoverContextMenu:
    """Context menu includes cover photo actions."""

    def test_cover_submenu_exists_single_selection(self, qtbot):
        """Context menu has a 'Cover Photo' submenu for single selection."""
        from src.gui.widgets.context_menu_helper import GalleryContextMenuHelper

        helper = GalleryContextMenuHelper()
        helper.main_window = MagicMock()

        mock_item = MagicMock()
        mock_item.cover_source_path = None
        mock_item.status = "ready"
        helper.main_window.queue_manager.items = {"/tmp/test": mock_item}
        helper.main_window.queue_manager.get_item.return_value = mock_item

        menu = helper.create_context_menu(None, ["/tmp/test"])

        # Find Cover Photo submenu
        submenu_texts = [a.text() for a in menu.actions() if a.menu()]
        assert "Cover Photo" in submenu_texts

    def test_no_cover_submenu_multi_selection(self, qtbot):
        """No cover submenu when multiple items selected."""
        from src.gui.widgets.context_menu_helper import GalleryContextMenuHelper

        helper = GalleryContextMenuHelper()
        helper.main_window = MagicMock()

        mock_item = MagicMock()
        mock_item.cover_source_path = None
        mock_item.status = "ready"
        helper.main_window.queue_manager.items = {
            "/tmp/test1": mock_item,
            "/tmp/test2": mock_item,
        }
        helper.main_window.queue_manager.get_item.return_value = mock_item

        menu = helper.create_context_menu(None, ["/tmp/test1", "/tmp/test2"])

        submenu_texts = [a.text() for a in menu.actions() if a.menu()]
        assert "Cover Photo" not in submenu_texts

    def test_clear_cover_only_when_cover_set(self, qtbot):
        """Clear Cover action only appears when item has a cover."""
        from src.gui.widgets.context_menu_helper import GalleryContextMenuHelper

        helper = GalleryContextMenuHelper()
        helper.main_window = MagicMock()

        # Item WITHOUT cover
        mock_item_no_cover = MagicMock()
        mock_item_no_cover.cover_source_path = None
        mock_item_no_cover.status = "ready"
        helper.main_window.queue_manager.items = {"/tmp/test": mock_item_no_cover}
        helper.main_window.queue_manager.get_item.return_value = mock_item_no_cover

        menu = helper.create_context_menu(None, ["/tmp/test"])
        cover_submenu = None
        for a in menu.actions():
            if a.menu() and a.text() == "Cover Photo":
                cover_submenu = a.menu()
        assert cover_submenu is not None
        action_texts = [a.text() for a in cover_submenu.actions()]
        assert "Set as Cover..." in action_texts
        assert "Clear Cover" not in action_texts

        # Item WITH cover
        mock_item_with_cover = MagicMock()
        mock_item_with_cover.cover_source_path = "/tmp/test/cover.jpg"
        mock_item_with_cover.status = "ready"
        helper.main_window.queue_manager.items = {"/tmp/test": mock_item_with_cover}
        helper.main_window.queue_manager.get_item.return_value = mock_item_with_cover

        menu2 = helper.create_context_menu(None, ["/tmp/test"])
        cover_submenu2 = None
        for a in menu2.actions():
            if a.menu() and a.text() == "Cover Photo":
                cover_submenu2 = a.menu()
        assert cover_submenu2 is not None
        action_texts2 = [a.text() for a in cover_submenu2.actions()]
        assert "Set as Cover..." in action_texts2
        assert "Clear Cover" in action_texts2
