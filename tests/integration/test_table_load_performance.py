"""
Integration tests for table loading performance with icon caching and batch queries.

Tests verify that:
1. Table loading uses icon cache effectively
2. Table loading uses batch database queries
3. Combined optimizations provide 2-3x speedup
4. Large datasets (100+ galleries) load quickly
"""

import os
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtWidgets import QApplication

from src.storage.database import QueueStore
from src.storage.queue_manager import QueueManager
from src.gui.icon_manager import IconManager


@pytest.fixture
def qt_app():
    """Ensure QApplication exists"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_assets_dir(tmp_path):
    """Create temporary assets directory with test icons"""
    assets = tmp_path / "assets"
    assets.mkdir()

    # Create all required icon files
    icon_files = [
        "status_completed-light.png",
        "status_completed-dark.png",
        "status_failed-light.png",
        "status_failed-dark.png",
        "status_uploading-light.png",
        "status_uploading-dark.png",
        "status_uploading-001-light.png",
        "status_uploading-001-dark.png",
        "status_uploading-002-light.png",
        "status_uploading-002-dark.png",
        "status_uploading-003-light.png",
        "status_uploading-003-dark.png",
        "status_uploading-004-light.png",
        "status_uploading-004-dark.png",
        "status_ready-light.png",
        "status_ready-dark.png",
        "status_pending-light.png",
        "status_pending-dark.png",
        "status_incomplete-light.png",
        "status_incomplete-dark.png",
        "status_paused-light.png",
        "status_paused-dark.png",
        "status_queued-light.png",
        "status_queued-dark.png",
        "status_scan_failed-light.png",
        "status_scan_failed-dark.png",
        "status_error-light.png",
        "status_error-dark.png",
        "status_scanning-light.png",
        "status_scanning-dark.png",
        "status_validating-light.png",
        "status_validating-dark.png",
        "action_start-light.png",
        "action_start-dark.png",
        "action_stop-light.png",
        "action_stop-dark.png",
        "action_view-light.png",
        "action_view-dark.png",
        "renamed_true-light.png",
        "renamed_true-dark.png",
        "renamed_false-light.png",
        "renamed_false-dark.png",
    ]

    for icon_file in icon_files:
        (assets / icon_file).write_bytes(b"fake icon data")

    return str(assets)


@pytest.fixture
def populated_db(tmp_path):
    """Create database with 100 galleries for realistic testing"""
    db_path = str(tmp_path / "test.db")
    store = QueueStore(db_path)

    # Create 100 galleries with varied statuses
    statuses = ['completed', 'ready', 'uploading', 'incomplete', 'failed', 'queued']
    galleries = []

    for i in range(100):
        gallery_data = {
            'path': f'/fake/gallery_{i:03d}',
            'name': f'Test Gallery {i}',
            'status': statuses[i % len(statuses)],
            'added_time': 1700000000 + i,
            'total_images': 10 + (i % 20),
            'uploaded_images': (5 + (i % 15)) if i % 2 == 0 else 0,
            'scan_complete': True,
            'gallery_id': f'TEST{i:05d}',
        }
        galleries.append(gallery_data)

    store.bulk_upsert(galleries)

    # Add file host uploads to 50% of galleries
    for i in range(0, 100, 2):
        for host in ['rapidgator', 'gofile']:
            store.add_file_host_upload(
                gallery_path=f'/fake/gallery_{i:03d}',
                host_name=host,
                status='completed'
            )

    return store


class TestTableLoadIconCaching:
    """Test that table loading benefits from icon caching"""

    def test_table_load_uses_cached_icons(self, qt_app, temp_assets_dir, populated_db):
        """Verify table loading benefits from icon cache"""
        # Create icon manager
        icon_manager = IconManager(temp_assets_dir)

        # Simulate loading table: request status icon for each gallery
        all_items = populated_db.load_all_items()

        # First pass - populate cache
        for item in all_items:
            status = item['status']
            icon_manager.get_status_icon(status, 'light')

        # Get cache stats after first pass
        stats_after_first = icon_manager.get_cache_stats()

        # Second pass - should use cache
        for item in all_items:
            status = item['status']
            icon_manager.get_status_icon(status, 'light')

        # Get cache stats after second pass
        stats_after_second = icon_manager.get_cache_stats()

        # Verify cache was used
        cache_hits = stats_after_second['hits'] - stats_after_first['hits']
        assert cache_hits == 100, f"Should have 100 cache hits (one per gallery), got {cache_hits}"

        # Verify no additional disk I/O
        disk_loads_first = stats_after_first['disk_loads']
        disk_loads_second = stats_after_second['disk_loads']
        assert disk_loads_first == disk_loads_second, \
            "Second pass should not load any icons from disk"

        # Verify hit rate is high
        hit_rate = stats_after_second['hit_rate']
        assert hit_rate > 50, f"Cache hit rate should be >50% after two passes, got {hit_rate:.1f}%"

        print(f"\nIcon cache performance:")
        print(f"  Total icon requests: {stats_after_second['hits'] + stats_after_second['misses']}")
        print(f"  Cache hits: {stats_after_second['hits']}")
        print(f"  Cache misses: {stats_after_second['misses']}")
        print(f"  Disk I/O operations: {stats_after_second['disk_loads']}")
        print(f"  Hit rate: {hit_rate:.1f}%")
        print(f"  Disk I/O saved: {stats_after_second['hits']} operations")

    def test_icon_cache_hit_rate_realistic(self, qt_app, temp_assets_dir, populated_db):
        """Verify realistic cache hit rate (>95%) with typical usage"""
        icon_manager = IconManager(temp_assets_dir)
        all_items = populated_db.load_all_items()

        # Simulate realistic table usage: load table 10 times (scroll, refresh, etc.)
        for _ in range(10):
            for item in all_items:
                status = item['status']
                icon_manager.get_status_icon(status, 'light')

        stats = icon_manager.get_cache_stats()
        hit_rate = stats['hit_rate']

        # With 6 unique statuses and 100 galleries loaded 10 times:
        # First load: 6 misses, 94 hits
        # Remaining 9 loads: 900 hits
        # Expected hit rate: 994/1000 = 99.4%

        assert hit_rate > 95, f"Cache hit rate should be >95% with realistic usage, got {hit_rate:.1f}%"

        print(f"\nRealistic usage (10 table loads):")
        print(f"  Hit rate: {hit_rate:.1f}%")
        print(f"  Disk I/O saved: {stats['hits']:,} operations")


class TestTableLoadBatchQueries:
    """Test that table loading uses batch database queries"""

    def test_table_load_uses_batch_query(self, populated_db):
        """Verify table loading uses batch query instead of individual queries"""
        # Mock the individual query method to count calls
        original_method = populated_db.get_file_host_uploads
        call_count = {'individual': 0}

        def tracked_individual_query(path):
            call_count['individual'] += 1
            return original_method(path)

        # Replace method temporarily
        populated_db.get_file_host_uploads = tracked_individual_query

        # Simulate table load WITHOUT batch query (old way)
        all_items = populated_db.load_all_items()
        for item in all_items:
            populated_db.get_file_host_uploads(item['path'])

        individual_calls = call_count['individual']

        # Restore original method
        populated_db.get_file_host_uploads = original_method

        # Now use batch query (new way)
        batch_uploads = populated_db.get_all_file_host_uploads_batch()

        # Verify batch query returned same data with just 1 call
        assert len(batch_uploads) == 50, "Batch query should return uploads for 50 galleries"

        print(f"\nBatch query comparison:")
        print(f"  Individual queries: {individual_calls} calls")
        print(f"  Batch query: 1 call")
        print(f"  Reduction: {individual_calls}x fewer database calls")

        assert individual_calls == 100, "Individual approach should make 100 calls"

    def test_batch_query_performance_vs_individual(self, populated_db):
        """Verify batch query is significantly faster than individual queries"""
        all_items = populated_db.load_all_items()

        # Time individual queries
        start = time.time()
        individual_uploads = {}
        for item in all_items:
            uploads = populated_db.get_file_host_uploads(item['path'])
            if uploads:
                individual_uploads[item['path']] = uploads
        individual_time = time.time() - start

        # Time batch query
        start = time.time()
        batch_uploads = populated_db.get_all_file_host_uploads_batch()
        batch_time = time.time() - start

        speedup = individual_time / batch_time if batch_time > 0 else float('inf')

        print(f"\nDatabase query performance:")
        print(f"  Individual queries: {individual_time*1000:.2f}ms")
        print(f"  Batch query:        {batch_time*1000:.2f}ms")
        print(f"  Speedup:            {speedup:.1f}x")

        # Batch should be at least 10x faster (conservative)
        assert speedup >= 10, f"Batch query should be >=10x faster, got {speedup:.1f}x"


class TestCombinedOptimizations:
    """Test combined icon caching + batch query optimizations"""

    def test_combined_optimizations_speedup(self, qt_app, temp_assets_dir, populated_db):
        """Verify combined optimizations provide 2-3x speedup"""
        icon_manager = IconManager(temp_assets_dir)
        all_items = populated_db.load_all_items()

        # Simulate UNOPTIMIZED table load
        # - Individual database queries for each gallery
        # - No icon caching (fresh IconManager each time)

        start = time.time()

        # Get uploads individually (old way)
        for item in all_items:
            populated_db.get_file_host_uploads(item['path'])

        # Load icons without cache (simulate no caching)
        fresh_manager = IconManager(temp_assets_dir)
        for item in all_items:
            fresh_manager.get_status_icon(item['status'], 'light')

        unoptimized_time = time.time() - start

        # Simulate OPTIMIZED table load
        # - Batch database query
        # - Icon caching enabled

        # Pre-warm icon cache
        for item in all_items[:10]:  # Load a few icons to simulate real usage
            icon_manager.get_status_icon(item['status'], 'light')

        start = time.time()

        # Batch query (new way)
        batch_uploads = populated_db.get_all_file_host_uploads_batch()

        # Load icons with cache
        for item in all_items:
            icon_manager.get_status_icon(item['status'], 'light')

        optimized_time = time.time() - start

        speedup = unoptimized_time / optimized_time if optimized_time > 0 else float('inf')

        print(f"\nCombined optimization performance:")
        print(f"  Unoptimized: {unoptimized_time*1000:.2f}ms")
        print(f"  Optimized:   {optimized_time*1000:.2f}ms")
        print(f"  Speedup:     {speedup:.1f}x")

        # Combined optimizations should provide at least 2x speedup
        assert speedup >= 2.0, f"Combined optimizations should provide >=2x speedup, got {speedup:.1f}x"

    def test_optimizations_scale_with_dataset_size(self, qt_app, temp_assets_dir, tmp_path):
        """Verify optimizations scale well with larger datasets"""
        icon_manager = IconManager(temp_assets_dir)
        timings = {}

        for gallery_count in [50, 100, 200]:
            # Create fresh database
            db_path = str(tmp_path / f"test_{gallery_count}.db")
            store = QueueStore(db_path)

            # Create galleries
            galleries = []
            statuses = ['completed', 'ready', 'uploading', 'incomplete', 'failed']
            for i in range(gallery_count):
                gallery_data = {
                    'path': f'/fake/gallery_{i:04d}',
                    'name': f'Gallery {i}',
                    'status': statuses[i % len(statuses)],
                    'added_time': 1700000000 + i,
                }
                galleries.append(gallery_data)

            store.bulk_upsert(galleries)

            # Add uploads to half the galleries
            for i in range(0, gallery_count, 2):
                store.add_file_host_upload(
                    gallery_path=f'/fake/gallery_{i:04d}',
                    host_name='rapidgator',
                    status='completed'
                )

            # Time optimized load
            start = time.time()

            all_items = store.load_all_items()
            batch_uploads = store.get_all_file_host_uploads_batch()

            for item in all_items:
                icon_manager.get_status_icon(item['status'], 'light')

            elapsed = time.time() - start
            timings[gallery_count] = elapsed

        print(f"\nScaling with dataset size (optimized):")
        for count, elapsed in timings.items():
            print(f"  {count} galleries: {elapsed*1000:.2f}ms")

        # Verify scaling is reasonable
        # 4x data (50 -> 200) should take < 8x time
        if 50 in timings and 200 in timings:
            ratio = timings[200] / timings[50] if timings[50] > 0 else 0
            assert ratio < 8, f"Scaling seems poor: 4x data took {ratio:.1f}x time"


class TestLargeDatasetPerformance:
    """Test performance with large realistic datasets"""

    def test_large_dataset_loads_quickly(self, qt_app, temp_assets_dir, tmp_path):
        """Verify 500+ galleries load in reasonable time"""
        # Create database with 500 galleries
        db_path = str(tmp_path / "large_test.db")
        store = QueueStore(db_path)

        statuses = ['completed', 'ready', 'uploading', 'incomplete', 'failed', 'queued']
        galleries = []

        for i in range(500):
            gallery_data = {
                'path': f'/fake/gallery_{i:04d}',
                'name': f'Gallery {i}',
                'status': statuses[i % len(statuses)],
                'added_time': 1700000000 + i,
                'total_images': 10 + (i % 30),
                'uploaded_images': (5 + (i % 20)) if i % 2 == 0 else 0,
            }
            galleries.append(gallery_data)

        store.bulk_upsert(galleries)

        # Add uploads to 40% of galleries
        for i in range(0, 500, 5):
            for host in ['rapidgator', 'gofile']:
                store.add_file_host_upload(
                    gallery_path=f'/fake/gallery_{i:04d}',
                    host_name=host,
                    status='completed' if i % 2 == 0 else 'pending'
                )

        # Create icon manager
        icon_manager = IconManager(temp_assets_dir)

        # Simulate complete table load
        start = time.time()

        # Load all galleries
        all_items = store.load_all_items()

        # Batch query for uploads
        batch_uploads = store.get_all_file_host_uploads_batch()

        # Load icons with cache
        for item in all_items:
            icon_manager.get_status_icon(item['status'], 'light')

        total_time = time.time() - start

        print(f"\nLarge dataset performance (500 galleries):")
        print(f"  Total load time: {total_time*1000:.2f}ms")
        print(f"  Time per gallery: {total_time/500*1000:.3f}ms")

        # Get icon cache stats
        stats = icon_manager.get_cache_stats()
        print(f"\n  Icon cache stats:")
        print(f"    Hit rate: {stats['hit_rate']:.1f}%")
        print(f"    Disk I/O saved: {stats['hits']:,} operations")

        # Should load in under 1 second (generous limit for test environment)
        assert total_time < 1.0, f"500 galleries should load in <1s, took {total_time:.2f}s"

        # Icon cache hit rate should be excellent
        assert stats['hit_rate'] > 98, f"Icon cache hit rate should be >98%, got {stats['hit_rate']:.1f}%"


class TestMemoryEfficiency:
    """Test memory efficiency of optimizations"""

    def test_icon_cache_memory_usage(self, qt_app, temp_assets_dir, populated_db):
        """Verify icon cache doesn't use excessive memory"""
        icon_manager = IconManager(temp_assets_dir)
        all_items = populated_db.load_all_items()

        # Load all icons
        for item in all_items:
            icon_manager.get_status_icon(item['status'], 'light')

        stats = icon_manager.get_cache_stats()

        # Should only cache unique icons (not one per gallery)
        # With 6 statuses, should have ~6 cached icons
        assert stats['cached_icons'] <= 10, \
            f"Icon cache should only store unique icons, got {stats['cached_icons']}"

        print(f"\nMemory efficiency:")
        print(f"  Galleries loaded: {len(all_items)}")
        print(f"  Unique icons cached: {stats['cached_icons']}")
        print(f"  Memory efficiency: {len(all_items) / stats['cached_icons']:.1f}x reuse")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
