"""Tests for generalized gallery table Online status column."""

import os
import pytest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt


class TestGetWorstStatusForGallery:
    """Tests for QueueStore.get_worst_status_for_gallery()."""

    @pytest.fixture
    def store(self):
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        from src.storage.database import QueueStore
        store = QueueStore(db_path=path)
        yield store
        try:
            os.unlink(path)
        except OSError:
            pass

    def _insert_gallery(self, store, path):
        from src.storage.database import _connect
        import time
        conn = _connect(store.db_path)
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, ?)",
            (path, path.split('/')[-1], 'completed', int(time.time()))
        )
        gal_id = conn.execute("SELECT id FROM galleries WHERE path = ?", (path,)).fetchone()[0]
        conn.close()
        return gal_id

    def _insert_scan_result(self, store, gallery_fk, host_type, host_id, status, online, total):
        import time
        from src.storage.database import _connect
        conn = _connect(store.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO host_scan_results "
            "(gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (gallery_fk, host_type, host_id, status, online, total, int(time.time()))
        )
        conn.close()

    def test_single_host_online(self, store):
        gal_id = self._insert_gallery(store, '/test/a')
        self._insert_scan_result(store, gal_id, 'image', 'imx', 'online', 10, 10)
        result = store.get_worst_status_for_gallery(gal_id)
        assert result['worst_status'] == 'online'

    def test_multi_host_worst_is_offline(self, store):
        gal_id = self._insert_gallery(store, '/test/b')
        self._insert_scan_result(store, gal_id, 'image', 'imx', 'online', 10, 10)
        self._insert_scan_result(store, gal_id, 'file', 'k2s', 'offline', 0, 5)
        result = store.get_worst_status_for_gallery(gal_id)
        assert result['worst_status'] == 'offline'

    def test_multi_host_worst_is_partial(self, store):
        gal_id = self._insert_gallery(store, '/test/c')
        self._insert_scan_result(store, gal_id, 'image', 'imx', 'online', 10, 10)
        self._insert_scan_result(store, gal_id, 'image', 'turbo', 'partial', 7, 10)
        result = store.get_worst_status_for_gallery(gal_id)
        assert result['worst_status'] == 'partial'

    def test_no_results_returns_none(self, store):
        gal_id = self._insert_gallery(store, '/test/d')
        result = store.get_worst_status_for_gallery(gal_id)
        assert result is None

    def test_per_host_breakdown(self, store):
        gal_id = self._insert_gallery(store, '/test/e')
        self._insert_scan_result(store, gal_id, 'image', 'imx', 'online', 10, 10)
        self._insert_scan_result(store, gal_id, 'file', 'rapidgator', 'partial', 3, 5)
        result = store.get_worst_status_for_gallery(gal_id)
        assert len(result['hosts']) == 2
        assert any(h['host_id'] == 'imx' for h in result['hosts'])
        assert any(h['host_id'] == 'rapidgator' for h in result['hosts'])

    def test_total_aggregation(self, store):
        gal_id = self._insert_gallery(store, '/test/f')
        self._insert_scan_result(store, gal_id, 'image', 'imx', 'online', 10, 10)
        self._insert_scan_result(store, gal_id, 'file', 'k2s', 'partial', 3, 5)
        result = store.get_worst_status_for_gallery(gal_id)
        assert result['total_online'] == 13
        assert result['total_items'] == 15


class TestGalleryTableMultiHostStatus:
    """Tests for the generalized Online column on the gallery table."""

    @pytest.fixture
    def table(self, qtbot):
        from src.gui.widgets.gallery_table import GalleryTableWidget
        table = GalleryTableWidget()
        qtbot.addWidget(table)
        return table

    def test_set_online_status_replaces_imx_method(self, table):
        assert hasattr(table, 'set_online_status')

    def test_set_online_status_with_tooltip(self, table, qtbot):
        table.insertRow(0)
        from PyQt6.QtWidgets import QTableWidgetItem
        table.setItem(0, 0, QTableWidgetItem("test"))

        host_details = [
            {'host_id': 'imx', 'online': 10, 'total': 10, 'status': 'online'},
            {'host_id': 'k2s', 'online': 3, 'total': 5, 'status': 'partial'},
        ]
        table.set_online_status(0, 13, 15, '2026-03-10 14:00', host_details=host_details)

        col = table.COL_ONLINE_IMX  # Use existing column constant
        item = table.item(0, col)
        assert item is not None
        tooltip = item.toolTip()
        assert 'IMX' in tooltip or 'imx' in tooltip
        assert 'K2S' in tooltip or 'k2s' in tooltip
