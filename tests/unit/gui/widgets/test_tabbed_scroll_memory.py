"""Each tab reopens scrolled to the gallery that was at the top when it was left.

Before 2026-10-24 the scroll position lived only in memory and was restored
before the tab's filter hid the other tabs' rows, so it landed in the wrong
place, and every restart opened every tab at the top.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QTableWidgetItem

from src.gui.tab_manager import TabManager
from src.gui.widgets.gallery_table import GalleryTableWidget
from src.gui.widgets.tabbed_gallery import TabbedGalleryWidget

ROWS = 200


class _FakeTabManager:
    """Main holds the first 150 rows, Tab1 the last 50: tabs of different sizes."""

    def __init__(self):
        self.last_active_tab = "Main"
        self.anchors = {}

    def get_visible_tab_names(self):
        return ["Main", "Tab1"]

    def load_tab_galleries(self, tab_name):
        in_main = tab_name == "Main"
        return [{"path": f"/g/{i}"} for i in range(ROWS) if (i < 150) == in_main]

    def get_scroll_anchor(self, tab_name):
        return self.anchors.get(tab_name, "")

    def set_scroll_anchors(self, anchors):
        self.anchors.update({t: p for t, p in anchors.items() if t and p})


def _make_widget(qtbot, manager):
    widget = TabbedGalleryWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 400)
    widget.show()
    qtbot.waitExposed(widget)
    widget.set_tab_manager(manager)
    widget.table.setRowCount(ROWS)
    for row in range(ROWS):
        item = QTableWidgetItem(f"Gallery {row}")
        item.setData(Qt.ItemDataRole.UserRole, f"/g/{row}")
        widget.table.setItem(row, GalleryTableWidget.COL_NAME, item)
    widget.refresh_filter()
    _settle(widget, qtbot)
    return widget


def _settle(widget, qtbot):
    """Under load the filter overruns its 10 ms budget and finishes on timers."""
    qtbot.waitUntil(lambda: not widget._filter_in_progress, timeout=5000)
    qtbot.wait(10)  # let the table lay out its rows and scroll range


def _switch(widget, qtbot, tab_name):
    widget.switch_to_tab(tab_name)
    _settle(widget, qtbot)


def _scroll_top_to(widget, row):
    widget.table.scrollToItem(widget.table.item(row, GalleryTableWidget.COL_NAME),
                              QAbstractItemView.ScrollHint.PositionAtTop)


def _top_path(widget):
    QApplication.processEvents()  # lay out the rows the filter just hid or showed
    row = widget.table.rowAt(0)
    return widget.table.item(row, GalleryTableWidget.COL_NAME).data(Qt.ItemDataRole.UserRole)


@pytest.mark.unit
class TestScrollMemory:

    def test_switching_back_returns_to_the_same_gallery(self, qtbot):
        widget = _make_widget(qtbot, _FakeTabManager())
        _scroll_top_to(widget, 120)
        assert _top_path(widget) == "/g/120"

        _switch(widget, qtbot, "Tab1")
        _scroll_top_to(widget, 175)
        _switch(widget, qtbot, "Main")
        assert _top_path(widget) == "/g/120"

        _switch(widget, qtbot, "Tab1")
        assert _top_path(widget) == "/g/175"

    def test_position_survives_a_restart(self, qtbot):
        manager = _FakeTabManager()
        first = _make_widget(qtbot, manager)
        _switch(first, qtbot, "Tab1")
        _scroll_top_to(first, 175)
        _switch(first, qtbot, "Main")
        _scroll_top_to(first, 100)
        first.save_scroll_positions()

        second = _make_widget(qtbot, manager)
        second.restore_scroll_position()
        assert _top_path(second) == "/g/100"
        _switch(second, qtbot, "Tab1")
        assert _top_path(second) == "/g/175"

    def test_opening_on_a_small_tab_then_switching_to_a_big_one(self, qtbot):
        """The scroll range still fits the small tab when the big one is shown."""
        manager = _FakeTabManager()
        manager.last_active_tab = "Tab1"
        manager.anchors["Main"] = "/g/120"
        widget = _make_widget(qtbot, manager)
        assert widget.current_tab == "Tab1"

        _switch(widget, qtbot, "Main")
        assert _top_path(widget) == "/g/120"

    def test_waits_for_a_filter_that_finishes_in_later_slices(self, qtbot):
        """Big tabs overrun the filter's 10 ms budget and finish on timers."""
        manager = _FakeTabManager()
        manager.anchors["Main"] = "/g/120"
        widget = _make_widget(qtbot, manager)
        widget._filter_in_progress = True
        widget.restore_scroll_position()
        assert widget.table.verticalScrollBar().value() == 0

        main_paths = {f"/g/{i}" for i in range(150)}
        widget._continue_filter_with_cache(0, ROWS, "Main", main_paths, "Main_200_0", {},
                                           widget._filter_generation)
        assert _top_path(widget) == "/g/120"

    def test_unfinished_filter_of_the_previous_tab_stops(self, qtbot):
        """Leftover slices of Main's filter must not re-hide Tab1's rows."""
        widget = _make_widget(qtbot, _FakeTabManager())
        main_run = widget._filter_generation
        _switch(widget, qtbot, "Tab1")
        main_paths = {f"/g/{i}" for i in range(150)}
        widget._continue_filter_with_cache(0, ROWS, "Main", main_paths, "Main_200_0", {}, main_run)
        assert not widget.table.isRowHidden(175)
        assert widget.table.isRowHidden(20)

    def test_missing_gallery_leaves_the_list_where_it_is(self, qtbot):
        manager = _FakeTabManager()
        manager.anchors["Main"] = "/g/gone"
        widget = _make_widget(qtbot, manager)
        widget.restore_scroll_position()
        assert widget.table.verticalScrollBar().value() == 0

    def test_mock_tab_manager_is_tolerated(self, qtbot):
        widget = _make_widget(qtbot, _FakeTabManager())
        widget.tab_manager = MagicMock()
        widget.tab_manager.load_tab_galleries.return_value = []
        widget.restore_scroll_position()
        widget.save_scroll_positions()


@pytest.mark.unit
class TestTabManagerKeepsAnchors:

    @pytest.fixture
    def store(self):
        store = MagicMock()
        store.get_all_tabs.return_value = [{"name": "Main"}, {"name": "AnchorTab"}]
        return store

    def test_anchors_are_read_back_by_the_next_instance(self, store):
        TabManager(store).set_scroll_anchors({"AnchorTab": "/g/7"})
        assert TabManager(store).get_scroll_anchor("AnchorTab") == "/g/7"

    def test_anchor_follows_a_renamed_tab(self, store):
        manager = TabManager(store)
        manager.set_scroll_anchors({"AnchorTab": "/g/9"})
        manager._handle_tab_rename("AnchorTab", "Renamed")
        assert manager.get_scroll_anchor("Renamed") == "/g/9"
        assert manager.get_scroll_anchor("AnchorTab") == ""

    def test_anchor_of_a_deleted_tab_is_dropped(self, store):
        manager = TabManager(store)
        manager.set_scroll_anchors({"AnchorTab": "/g/3"})
        store.get_all_tabs.return_value = [{"name": "Main"}]
        assert TabManager(store).get_scroll_anchor("AnchorTab") == ""
