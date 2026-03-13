"""Tests for IMX bridge -- routing IMX status check results to host_scan_results table."""

import os
import time
import pytest
from unittest.mock import MagicMock, patch, call

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


class TestImxBridge:
    """Verify ImageStatusChecker writes to host_scan_results after IMX check."""

    @pytest.fixture
    def checker(self, qtbot):
        from src.gui.dialogs.image_status_checker import ImageStatusChecker
        parent = MagicMock()
        qm = MagicMock()
        rw = MagicMock()
        gt = MagicMock()
        gt.rowCount.return_value = 0
        checker = ImageStatusChecker(parent=parent, queue_manager=qm, rename_worker=rw, gallery_table=gt)
        return checker

    def test_on_completed_calls_bulk_upsert(self, checker):
        """_on_completed should call bulk_upsert_scan_results with IMX results."""
        checker._check_in_progress = True
        checker._cancelled = False
        checker._start_time = time.time() - 1.0
        checker._galleries_data = [
            {'db_id': 1, 'path': '/test/a'},
            {'db_id': 2, 'path': '/test/b'},
        ]

        results = {
            '/test/a': {'online': 10, 'total': 10},
            '/test/b': {'online': 7, 'total': 10},
        }

        checker._on_completed(results)

        store = checker.queue_manager.store
        store.bulk_upsert_scan_results.assert_called_once()
        upserted = store.bulk_upsert_scan_results.call_args[0][0]
        assert len(upserted) == 2

        for row in upserted:
            assert row[1] == 'image'  # host_type
            assert row[2] == 'imx'    # host_id
            assert row[3] in ('online', 'partial', 'offline')

    def test_online_gallery_gets_online_status(self, checker):
        """Gallery with all images online should get status='online'."""
        checker._check_in_progress = True
        checker._cancelled = False
        checker._start_time = time.time() - 1.0
        checker._galleries_data = [{'db_id': 1, 'path': '/test/a'}]

        results = {'/test/a': {'online': 10, 'total': 10}}
        checker._on_completed(results)

        upserted = checker.queue_manager.store.bulk_upsert_scan_results.call_args[0][0]
        assert upserted[0][3] == 'online'

    def test_partial_gallery_gets_partial_status(self, checker):
        """Gallery with some offline images should get status='partial'."""
        checker._check_in_progress = True
        checker._cancelled = False
        checker._start_time = time.time() - 1.0
        checker._galleries_data = [{'db_id': 1, 'path': '/test/a'}]

        results = {'/test/a': {'online': 7, 'total': 10}}
        checker._on_completed(results)

        upserted = checker.queue_manager.store.bulk_upsert_scan_results.call_args[0][0]
        assert upserted[0][3] == 'partial'

    def test_offline_gallery_gets_offline_status(self, checker):
        """Gallery with zero online images should get status='offline'."""
        checker._check_in_progress = True
        checker._cancelled = False
        checker._start_time = time.time() - 1.0
        checker._galleries_data = [{'db_id': 1, 'path': '/test/a'}]

        results = {'/test/a': {'online': 0, 'total': 10}}
        checker._on_completed(results)

        upserted = checker.queue_manager.store.bulk_upsert_scan_results.call_args[0][0]
        assert upserted[0][3] == 'offline'

    def test_cancelled_check_skips_bridge(self, checker):
        """Cancelled check should NOT write to host_scan_results."""
        checker._check_in_progress = True
        checker._cancelled = True
        checker._start_time = time.time() - 1.0

        results = {'/test/a': {'online': 10, 'total': 10}}
        checker._on_completed(results)

        checker.queue_manager.store.bulk_upsert_scan_results.assert_not_called()

    def test_missing_db_id_skips_gallery(self, checker):
        """Gallery without db_id in _galleries_data should be skipped."""
        checker._check_in_progress = True
        checker._cancelled = False
        checker._start_time = time.time() - 1.0
        checker._galleries_data = [{'path': '/test/a'}]  # no db_id

        results = {'/test/a': {'online': 10, 'total': 10}}
        checker._on_completed(results)

        # bulk_upsert_scan_results should not be called since bridge_results is empty
        checker.queue_manager.store.bulk_upsert_scan_results.assert_not_called()
