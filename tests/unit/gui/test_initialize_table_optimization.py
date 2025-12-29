#!/usr/bin/env python3
"""
Unit tests for _initialize_table_from_queue() optimization

Tests verify the performance optimizations implemented in main_window:
1. setUpdatesEnabled(False) is used during bulk load
2. progress_callback called once (not per-row)
3. processEvents() NOT called during loop
4. Performance improvement (completes in <10 seconds for 997 items)

Author: Test Engineer Agent
Date: 2025-11-14
"""

import pytest
import sys
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from PyQt6.QtWidgets import QApplication, QTableWidgetItem
from PyQt6.QtCore import Qt

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.gui.widgets.gallery_table import GalleryTableWidget
from src.storage.queue_manager import GalleryQueueItem


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_queue_manager():
    """Mock QueueManager with realistic data"""
    manager = Mock()
    manager.get_item = Mock(return_value=None)
    manager.store = Mock()
    manager.store.get_file_host_uploads = Mock(return_value=[])
    manager.store.get_all_file_host_uploads_batch = Mock(return_value={})
    return manager


@pytest.fixture
def mock_main_window(qtbot, mock_queue_manager):
    """Create mock main window with real GalleryTableWidget"""
    window = Mock()
    window.queue_manager = mock_queue_manager
    window.gallery_table = GalleryTableWidget()
    window.gallery_table.queue_manager = mock_queue_manager
    window.path_to_row = {}
    window.row_to_path = {}
    window._initializing = False
    window._last_scan_states = {}
    window._file_host_uploads_cache = {}

    # Mock methods called during population
    window._set_status_cell_icon = Mock()
    window._set_status_text_cell = Mock()
    window._format_size_consistent = Mock(return_value="100 MiB")
    window._format_rate_consistent = Mock(return_value="500 KiB/s")
    window.get_theme_mode = Mock(return_value='light')
    window._populate_table_row = Mock()
    window._create_deferred_widgets = Mock()

    qtbot.addWidget(window.gallery_table)
    return window


@pytest.fixture
def create_gallery_items():
    """Factory fixture to create GalleryQueueItem objects"""
    def _create(count: int):
        items = []
        for i in range(count):
            item = Mock(spec=GalleryQueueItem)
            item.name = f"Gallery {i+1}"
            item.path = f"/tmp/gallery_{i+1}"
            item.status = "ready"
            item.gallery_id = f"id_{i+1}"
            item.gallery_url = f"https://imx.to/g/{i+1}"
            item.tab_name = "Main"
            item.tab_id = 1
            item.progress = 0.0
            item.total_images = 100
            item.uploaded_images = 0
            item.added_time = 1700000000 + i
            item.finished_time = None
            item.total_size = 1024 * 1024 * 100  # 100 MB
            item.current_kibps = 0.0
            item.final_kibps = 0.0
            item.template_name = "Default"
            item.scan_complete = False
            item.db_id = i + 1
            item.is_renamed = False
            items.append(item)
        return items
    return _create


# ============================================================================
# Test 1: setUpdatesEnabled(False) is used
# ============================================================================

class TestSetUpdatesEnabledOptimization:
    """Test that setUpdatesEnabled(False) is called before population"""

    def test_updates_disabled_during_population(self, mock_main_window, create_gallery_items, qtbot):
        """Verify setUpdatesEnabled(False) called before population, then True after"""
        # Arrange
        items = create_gallery_items(10)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track setUpdatesEnabled calls
        updates_enabled_calls = []
        original_set_updates = mock_main_window.gallery_table.setUpdatesEnabled

        def track_set_updates(enabled):
            updates_enabled_calls.append(enabled)
            return original_set_updates(enabled)

        mock_main_window.gallery_table.setUpdatesEnabled = track_set_updates

        # Import the method we're testing
        from src.gui.main_window import ImxUploadGUI

        # Act
        ImxUploadGUI._initialize_table_from_queue(mock_main_window)

        # Assert
        assert len(updates_enabled_calls) >= 2, "setUpdatesEnabled should be called at least twice"
        assert updates_enabled_calls[0] == False, "First call should disable updates"
        assert updates_enabled_calls[-1] == True, "Last call should re-enable updates"


    def test_updates_disabled_before_row_population(self, mock_main_window, create_gallery_items, qtbot):
        """Verify setUpdatesEnabled(False) called BEFORE any row population"""
        # Arrange
        items = create_gallery_items(5)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track order of calls
        call_order = []

        def track_set_updates(enabled):
            call_order.append(('setUpdatesEnabled', enabled))

        def track_populate_row(row, item):
            call_order.append(('populate_row', row))

        mock_main_window.gallery_table.setUpdatesEnabled = track_set_updates
        mock_main_window._populate_table_row = track_populate_row

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act
        ImxUploadGUI._initialize_table_from_queue(mock_main_window)

        # Assert
        assert len(call_order) > 0, "Should have recorded calls"
        assert call_order[0] == ('setUpdatesEnabled', False), \
            "setUpdatesEnabled(False) should be first call before any row population"

        # Find first populate_row call
        populate_indices = [i for i, (name, _) in enumerate(call_order) if name == 'populate_row']
        if populate_indices:
            first_populate_idx = populate_indices[0]
            # Verify setUpdatesEnabled(False) came before first populate
            assert any(
                call == ('setUpdatesEnabled', False)
                for call in call_order[:first_populate_idx]
            ), "setUpdatesEnabled(False) must be called before first row population"


    def test_updates_reenabled_after_population(self, mock_main_window, create_gallery_items, qtbot):
        """Verify setUpdatesEnabled(True) called AFTER all row population"""
        # Arrange
        items = create_gallery_items(5)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track order of calls
        call_order = []

        def track_set_updates(enabled):
            call_order.append(('setUpdatesEnabled', enabled))

        def track_populate_row(row, item):
            call_order.append(('populate_row', row))

        mock_main_window.gallery_table.setUpdatesEnabled = track_set_updates
        mock_main_window._populate_table_row = track_populate_row

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act
        ImxUploadGUI._initialize_table_from_queue(mock_main_window)

        # Assert
        # Find last populate_row call
        populate_indices = [i for i, (name, _) in enumerate(call_order) if name == 'populate_row']
        if populate_indices:
            last_populate_idx = populate_indices[-1]
            # Verify setUpdatesEnabled(True) came after last populate
            assert any(
                call == ('setUpdatesEnabled', True)
                for call in call_order[last_populate_idx:]
            ), "setUpdatesEnabled(True) must be called after last row population"


# ============================================================================
# Test 2: progress_callback called once
# ============================================================================

class TestProgressCallbackOptimization:
    """Test that progress_callback is called once, not per-row"""

    def test_progress_callback_called_once_for_997_items(self, mock_main_window, create_gallery_items, qtbot):
        """Verify progress_callback called ONCE for 997 items (not 997 times)"""
        # Arrange
        items = create_gallery_items(997)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track progress callback calls
        progress_calls = []

        def track_progress(current, total):
            progress_calls.append((current, total))

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act
        ImxUploadGUI._initialize_table_from_queue(mock_main_window, progress_callback=track_progress)

        # Assert
        assert len(progress_calls) == 1, \
            f"progress_callback should be called ONCE, not {len(progress_calls)} times"
        assert progress_calls[0] == (997, 997), \
            "progress_callback should be called with (997, 997) at completion"


    def test_progress_callback_not_called_during_loop(self, mock_main_window, create_gallery_items, qtbot):
        """Verify progress_callback is NOT called during the loop (only after)"""
        # Arrange
        items = create_gallery_items(100)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track when progress is called relative to row population
        call_order = []

        def track_progress(current, total):
            call_order.append(('progress_callback', current, total))

        def track_populate_row(row, item):
            call_order.append(('populate_row', row))

        mock_main_window._populate_table_row = track_populate_row

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act
        ImxUploadGUI._initialize_table_from_queue(mock_main_window, progress_callback=track_progress)

        # Assert
        # Find all populate_row calls
        populate_indices = [i for i, call in enumerate(call_order) if call[0] == 'populate_row']
        # Find progress_callback calls
        progress_indices = [i for i, call in enumerate(call_order) if call[0] == 'progress_callback']

        if populate_indices and progress_indices:
            last_populate_idx = max(populate_indices)
            first_progress_idx = min(progress_indices)

            assert first_progress_idx > last_populate_idx, \
                "progress_callback should be called AFTER all row population, not during"


    def test_progress_callback_optional(self, mock_main_window, create_gallery_items, qtbot):
        """Verify function works without progress_callback (optional parameter)"""
        # Arrange
        items = create_gallery_items(10)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act & Assert - should not raise exception
        try:
            ImxUploadGUI._initialize_table_from_queue(mock_main_window)
            success = True
        except Exception as e:
            success = False
            pytest.fail(f"Should work without progress_callback, but raised: {e}")

        assert success, "Should work without progress_callback parameter"


# ============================================================================
# Test 3: processEvents() NOT called during loop
# ============================================================================

class TestProcessEventsOptimization:
    """Test that QApplication.processEvents() is NOT called during initialization"""

    def test_process_events_not_called_during_init(self, mock_main_window, create_gallery_items, qtbot):
        """Verify QApplication.processEvents() is NOT called during table population"""
        # Arrange
        items = create_gallery_items(100)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track processEvents calls
        process_events_calls = []

        with patch.object(QApplication, 'processEvents') as mock_process_events:
            mock_process_events.side_effect = lambda: process_events_calls.append(1)

            # Import the method
            from src.gui.main_window import ImxUploadGUI

            # Act
            ImxUploadGUI._initialize_table_from_queue(mock_main_window)

            # Assert
            assert len(process_events_calls) == 0, \
                f"processEvents() should NOT be called during initialization, but was called {len(process_events_calls)} times"


    def test_minimal_process_events_calls(self, mock_main_window, create_gallery_items, qtbot):
        """Verify minimal processEvents() calls (if any) during initialization"""
        # Arrange
        items = create_gallery_items(500)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track processEvents calls with stack trace
        process_events_calls = []

        with patch.object(QApplication, 'processEvents') as mock_process_events:
            def track_call():
                import traceback
                stack = traceback.extract_stack()
                # Check if call is from _initialize_table_from_queue
                in_init_method = any('_initialize_table_from_queue' in str(frame) for frame in stack)
                if in_init_method:
                    process_events_calls.append(stack)

            mock_process_events.side_effect = track_call

            # Import the method
            from src.gui.main_window import ImxUploadGUI

            # Act
            ImxUploadGUI._initialize_table_from_queue(mock_main_window)

            # Assert
            # Allow up to 2 processEvents calls (for critical operations only)
            assert len(process_events_calls) <= 2, \
                f"processEvents() calls should be minimal (<= 2), but was called {len(process_events_calls)} times"


# ============================================================================
# Test 4: Performance improvement
# ============================================================================

class TestPerformanceImprovement:
    """Test that _initialize_table_from_queue completes quickly with 997 items"""

    @pytest.mark.performance
    def test_completes_under_10_seconds_for_997_items(self, mock_main_window, create_gallery_items, qtbot):
        """Verify _initialize_table_from_queue completes in <10 seconds for 997 items"""
        # Arrange
        items = create_gallery_items(997)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Use minimal mock for _populate_table_row to simulate real work
        def minimal_populate(row, item):
            # Simulate minimal work per row
            mock_main_window.path_to_row[item.path] = row
            mock_main_window.row_to_path[row] = item.path

        mock_main_window._populate_table_row = minimal_populate

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act
        start_time = time.time()
        ImxUploadGUI._initialize_table_from_queue(mock_main_window)
        elapsed_time = time.time() - start_time

        # Assert
        assert elapsed_time < 10.0, \
            f"Should complete in <10 seconds, but took {elapsed_time:.2f} seconds"

        print(f"\n✓ Performance test PASSED: 997 items initialized in {elapsed_time:.2f} seconds")


    @pytest.mark.performance
    def test_linear_scaling_performance(self, mock_main_window, create_gallery_items, qtbot):
        """Verify performance scales linearly (not quadratically) with item count"""
        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Use minimal mock for _populate_table_row
        def minimal_populate(row, item):
            mock_main_window.path_to_row[item.path] = row
            mock_main_window.row_to_path[row] = item.path

        mock_main_window._populate_table_row = minimal_populate

        # Test with different sizes
        test_sizes = [10, 50, 100, 500]
        times = []

        for size in test_sizes:
            # Reset state
            mock_main_window.path_to_row.clear()
            mock_main_window.row_to_path.clear()
            mock_main_window.gallery_table.setRowCount(0)

            # Create items
            items = create_gallery_items(size)
            mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

            # Measure time
            start = time.time()
            ImxUploadGUI._initialize_table_from_queue(mock_main_window)
            elapsed = time.time() - start
            times.append(elapsed)

            print(f"\n  {size} items: {elapsed:.4f} seconds")

        # Check scaling: time should scale roughly linearly
        # If scaling is quadratic, 500 items would take 2500x longer than 10 items
        # With linear scaling, it should take ~50x longer
        if len(times) >= 2 and times[0] > 0:
            scaling_factor = times[-1] / times[0]
            item_scaling = test_sizes[-1] / test_sizes[0]

            # Allow 2x overhead for linear scaling (50x items should take <100x time)
            assert scaling_factor < (item_scaling * 2), \
                f"Performance should scale linearly, but {test_sizes[-1]} items took {scaling_factor:.1f}x longer than {test_sizes[0]} items (expected <{item_scaling * 2}x)"

            print(f"✓ Linear scaling verified: {test_sizes[-1]} items took {scaling_factor:.1f}x longer than {test_sizes[0]} items")


# ============================================================================
# Test 5: Integration test with all optimizations
# ============================================================================

class TestFullOptimizationIntegration:
    """Integration test verifying all optimizations work together"""

    def test_all_optimizations_active(self, mock_main_window, create_gallery_items, qtbot):
        """Verify all optimizations are active in a single run"""
        # Arrange
        items = create_gallery_items(100)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track all optimization indicators
        updates_enabled_calls = []
        progress_calls = []
        process_events_calls = []

        def track_set_updates(enabled):
            updates_enabled_calls.append(enabled)

        def track_progress(current, total):
            progress_calls.append((current, total))

        mock_main_window.gallery_table.setUpdatesEnabled = track_set_updates

        with patch.object(QApplication, 'processEvents') as mock_process_events:
            mock_process_events.side_effect = lambda: process_events_calls.append(1)

            # Import the method
            from src.gui.main_window import ImxUploadGUI

            # Act
            start_time = time.time()
            ImxUploadGUI._initialize_table_from_queue(mock_main_window, progress_callback=track_progress)
            elapsed_time = time.time() - start_time

        # Assert all optimizations
        # 1. setUpdatesEnabled optimization
        assert len(updates_enabled_calls) >= 2, "setUpdatesEnabled should be called"
        assert updates_enabled_calls[0] == False, "Updates should be disabled first"
        assert updates_enabled_calls[-1] == True, "Updates should be re-enabled"

        # 2. Progress callback optimization
        assert len(progress_calls) == 1, "progress_callback should be called once"
        assert progress_calls[0] == (100, 100), "Progress should be reported at completion"

        # 3. processEvents optimization
        assert len(process_events_calls) <= 2, "processEvents should be minimal"

        # 4. Performance optimization
        assert elapsed_time < 5.0, f"Should complete quickly, took {elapsed_time:.2f}s"

        print(f"\n✓ All optimizations verified:")
        print(f"  - setUpdatesEnabled: {len(updates_enabled_calls)} calls")
        print(f"  - progress_callback: {len(progress_calls)} calls")
        print(f"  - processEvents: {len(process_events_calls)} calls")
        print(f"  - Time: {elapsed_time:.4f} seconds")


# ============================================================================
# Test 6: Batch loading optimization
# ============================================================================

class TestBatchLoadingOptimization:
    """Test the batch loading of file host uploads"""

    def test_batch_load_file_host_uploads(self, mock_main_window, create_gallery_items, qtbot):
        """Verify file host uploads are loaded in a single batch query"""
        # Arrange
        items = create_gallery_items(100)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        # Track batch load calls
        batch_load_calls = []

        def track_batch_load():
            batch_load_calls.append(1)
            return {"gallery_1": ["upload1.jpg"], "gallery_2": ["upload2.jpg"]}

        mock_main_window.queue_manager.store.get_all_file_host_uploads_batch = track_batch_load

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act
        ImxUploadGUI._initialize_table_from_queue(mock_main_window)

        # Assert
        assert len(batch_load_calls) == 1, \
            f"get_all_file_host_uploads_batch should be called ONCE, not {len(batch_load_calls)} times"


    def test_cache_populated_with_batch_results(self, mock_main_window, create_gallery_items, qtbot):
        """Verify _file_host_uploads_cache is populated with batch results"""
        # Arrange
        items = create_gallery_items(10)
        mock_main_window.queue_manager.get_all_items = Mock(return_value=items)

        batch_data = {
            "/tmp/gallery_1": ["file1.jpg", "file2.jpg"],
            "/tmp/gallery_2": ["file3.jpg"]
        }
        mock_main_window.queue_manager.store.get_all_file_host_uploads_batch = Mock(return_value=batch_data)

        # Import the method
        from src.gui.main_window import ImxUploadGUI

        # Act
        ImxUploadGUI._initialize_table_from_queue(mock_main_window)

        # Assert
        assert hasattr(mock_main_window, '_file_host_uploads_cache'), \
            "_file_host_uploads_cache should exist"
        assert mock_main_window._file_host_uploads_cache == batch_data, \
            "Cache should contain batch query results"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
