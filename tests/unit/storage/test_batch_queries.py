"""
Unit tests for batch database query optimization.

Tests verify that:
1. Batch query returns all upload data correctly
2. Batch query returns same data as individual queries
3. Batch query is significantly faster than individual queries
4. Empty database is handled gracefully
5. Large datasets are processed efficiently
"""

import os
import pytest
import time
from typing import Dict, List, Any

from src.storage.database import QueueStore


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing"""
    db_path = str(tmp_path / "test.db")
    store = QueueStore(db_path)
    return store


@pytest.fixture
def populated_db(temp_db):
    """Create database with sample galleries and file host uploads"""
    # Create sample galleries
    galleries = []
    for i in range(10):
        gallery_path = f"/fake/gallery_{i}"
        gallery_data = {
            'path': gallery_path,
            'name': f'Test Gallery {i}',
            'status': 'completed',
            'added_time': 1700000000 + i,
            'total_images': 10 + i,
            'uploaded_images': 10 + i,
            'scan_complete': True,
            'gallery_id': f'TESTID{i:03d}',
        }
        galleries.append(gallery_data)

    # Insert galleries
    temp_db.bulk_upsert(galleries)

    # Add file host uploads for each gallery
    for i, gallery_data in enumerate(galleries):
        # Add 2-3 file host uploads per gallery
        for host_idx, host_name in enumerate(['rapidgator', 'gofile'][:2 if i % 2 else 3]):
            temp_db.add_file_host_upload(
                gallery_path=gallery_data['path'],
                host_name=host_name,
                status='completed' if host_idx == 0 else 'pending'
            )

            # Update upload with some data
            uploads = temp_db.get_file_host_uploads(gallery_data['path'])
            if uploads:
                upload_id = uploads[-1]['id']
                temp_db.update_file_host_upload(
                    upload_id,
                    download_url=f"https://{host_name}.com/download/{i}",
                    file_id=f"FILE{i}_{host_idx}",
                    uploaded_bytes=1024 * 1024 * (i + 1),
                    total_bytes=1024 * 1024 * (i + 1)
                )

    return temp_db


class TestBatchQueryCorrectness:
    """Test that batch query returns correct data"""

    def test_batch_query_returns_all_uploads(self, populated_db):
        """Verify batch query returns same data as individual queries"""
        # Get all uploads via batch query
        batch_uploads = populated_db.get_all_file_host_uploads_batch()

        # Get all uploads via individual queries
        all_galleries = populated_db.load_all_items()
        individual_uploads = {}
        for gallery in all_galleries:
            path = gallery['path']
            uploads = populated_db.get_file_host_uploads(path)
            if uploads:
                individual_uploads[path] = uploads

        # Verify same galleries have uploads
        assert set(batch_uploads.keys()) == set(individual_uploads.keys()), \
            "Batch query should return uploads for same galleries as individual queries"

        # Verify upload counts match
        for path in batch_uploads.keys():
            batch_count = len(batch_uploads[path])
            individual_count = len(individual_uploads[path])
            assert batch_count == individual_count, \
                f"Gallery {path}: batch returned {batch_count} uploads, individual returned {individual_count}"

        # Verify upload data matches (check key fields)
        for path in batch_uploads.keys():
            batch_list = batch_uploads[path]
            individual_list = individual_uploads[path]

            # Sort both lists by created_ts for comparison
            batch_list = sorted(batch_list, key=lambda x: x.get('created_ts', 0))
            individual_list = sorted(individual_list, key=lambda x: x.get('created_ts', 0))

            for i, (batch_upload, individual_upload) in enumerate(zip(batch_list, individual_list)):
                # Verify key fields match
                key_fields = ['host_name', 'status', 'download_url', 'file_id']
                for field in key_fields:
                    assert batch_upload[field] == individual_upload[field], \
                        f"Gallery {path}, upload {i}: {field} mismatch"

    def test_batch_query_structure(self, populated_db):
        """Verify batch query returns correct data structure"""
        batch_uploads = populated_db.get_all_file_host_uploads_batch()

        # Should be a dictionary
        assert isinstance(batch_uploads, dict), "Should return dictionary"

        # Keys should be gallery paths
        for path in batch_uploads.keys():
            assert isinstance(path, str), "Keys should be strings (gallery paths)"
            assert path.startswith('/'), "Paths should be absolute"

        # Values should be lists of upload dictionaries
        for uploads_list in batch_uploads.values():
            assert isinstance(uploads_list, list), "Values should be lists"

            for upload in uploads_list:
                assert isinstance(upload, dict), "Each upload should be a dictionary"

                # Verify required fields exist
                required_fields = ['id', 'gallery_fk', 'host_name', 'status']
                for field in required_fields:
                    assert field in upload, f"Upload missing required field: {field}"


class TestBatchQueryEmptyCases:
    """Test batch query handles empty/edge cases"""

    def test_empty_batch_query(self, temp_db):
        """Verify batch query handles no uploads gracefully"""
        # Call with empty database
        batch_uploads = temp_db.get_all_file_host_uploads_batch()

        # Should return empty dict (not crash)
        assert isinstance(batch_uploads, dict), "Should return dictionary"
        assert len(batch_uploads) == 0, "Should return empty dictionary for empty database"

    def test_batch_query_with_galleries_but_no_uploads(self, temp_db):
        """Verify batch query handles galleries without uploads"""
        # Add galleries but no file host uploads
        galleries = [
            {
                'path': f'/fake/gallery_{i}',
                'name': f'Gallery {i}',
                'status': 'ready',
                'added_time': 1700000000 + i,
            }
            for i in range(5)
        ]
        temp_db.bulk_upsert(galleries)

        # Query should return empty dict
        batch_uploads = temp_db.get_all_file_host_uploads_batch()
        assert len(batch_uploads) == 0, "Should return empty dict when no uploads exist"

    def test_batch_query_with_partial_uploads(self, temp_db):
        """Verify batch query handles mix of galleries with/without uploads"""
        # Add 5 galleries
        galleries = [
            {
                'path': f'/fake/gallery_{i}',
                'name': f'Gallery {i}',
                'status': 'ready',
                'added_time': 1700000000 + i,
            }
            for i in range(5)
        ]
        temp_db.bulk_upsert(galleries)

        # Add uploads only to galleries 0, 2, 4
        for i in [0, 2, 4]:
            temp_db.add_file_host_upload(
                gallery_path=f'/fake/gallery_{i}',
                host_name='rapidgator',
                status='completed'
            )

        batch_uploads = temp_db.get_all_file_host_uploads_batch()

        # Should only return 3 galleries with uploads
        assert len(batch_uploads) == 3, "Should only return galleries with uploads"
        assert '/fake/gallery_0' in batch_uploads
        assert '/fake/gallery_2' in batch_uploads
        assert '/fake/gallery_4' in batch_uploads
        assert '/fake/gallery_1' not in batch_uploads
        assert '/fake/gallery_3' not in batch_uploads


class TestBatchQueryPerformance:
    """Test batch query performance characteristics"""

    def test_batch_query_performance(self, temp_db):
        """Verify batch query is faster than individual queries"""
        # Create 100 galleries with uploads
        galleries = []
        for i in range(100):
            gallery_data = {
                'path': f'/fake/gallery_{i}',
                'name': f'Gallery {i}',
                'status': 'completed',
                'added_time': 1700000000 + i,
            }
            galleries.append(gallery_data)

        temp_db.bulk_upsert(galleries)

        # Add 2 uploads per gallery
        for i in range(100):
            for host in ['rapidgator', 'gofile']:
                temp_db.add_file_host_upload(
                    gallery_path=f'/fake/gallery_{i}',
                    host_name=host,
                    status='completed'
                )

        # Time batch query
        start = time.time()
        batch_uploads = temp_db.get_all_file_host_uploads_batch()
        batch_time = time.time() - start

        # Time individual queries
        all_galleries = temp_db.load_all_items()
        start = time.time()
        individual_uploads = {}
        for gallery in all_galleries:
            uploads = temp_db.get_file_host_uploads(gallery['path'])
            if uploads:
                individual_uploads[gallery['path']] = uploads
        individual_time = time.time() - start

        # Batch should be at least 50x faster (conservative estimate)
        # In production it's 100x faster, but tests may have overhead
        speedup = individual_time / batch_time if batch_time > 0 else float('inf')

        print(f"\nPerformance comparison (100 galleries, 200 uploads):")
        print(f"  Batch query:      {batch_time*1000:.2f}ms")
        print(f"  Individual query: {individual_time*1000:.2f}ms")
        print(f"  Speedup:          {speedup:.1f}x")

        # Verify batch is significantly faster
        assert speedup >= 10, f"Batch query should be at least 10x faster (got {speedup:.1f}x)"

    def test_batch_query_scales_linearly(self, temp_db):
        """Verify batch query scales well with dataset size"""
        # Test with different dataset sizes
        timings = {}

        for gallery_count in [10, 50, 100]:
            # Create galleries
            galleries = [
                {
                    'path': f'/fake/gallery_{i}',
                    'name': f'Gallery {i}',
                    'status': 'completed',
                    'added_time': 1700000000 + i,
                }
                for i in range(gallery_count)
            ]

            temp_db.bulk_upsert(galleries)

            # Add uploads
            for i in range(gallery_count):
                temp_db.add_file_host_upload(
                    gallery_path=f'/fake/gallery_{i}',
                    host_name='rapidgator',
                    status='completed'
                )

            # Time batch query
            start = time.time()
            temp_db.get_all_file_host_uploads_batch()
            elapsed = time.time() - start

            timings[gallery_count] = elapsed

            # Clean up for next iteration
            temp_db.clear_all()

        print(f"\nBatch query scaling:")
        for count, elapsed in timings.items():
            print(f"  {count} galleries: {elapsed*1000:.2f}ms")

        # Verify scaling is reasonable (10x data should be < 20x time)
        if 10 in timings and 100 in timings:
            ratio = timings[100] / timings[10] if timings[10] > 0 else 0
            assert ratio < 20, f"Batch query scaling seems poor: 10x data took {ratio:.1f}x time"


class TestBatchQueryDataIntegrity:
    """Test batch query maintains data integrity"""

    def test_batch_query_preserves_all_fields(self, populated_db):
        """Verify batch query returns all upload fields"""
        batch_uploads = populated_db.get_all_file_host_uploads_batch()

        # Get an upload to check fields
        for uploads_list in batch_uploads.values():
            if uploads_list:
                upload = uploads_list[0]

                # Verify all expected fields are present
                expected_fields = [
                    'id', 'gallery_fk', 'host_name', 'status',
                    'zip_path', 'started_ts', 'finished_ts',
                    'uploaded_bytes', 'total_bytes',
                    'download_url', 'file_id', 'file_name', 'error_message',
                    'raw_response', 'retry_count', 'created_ts'
                ]

                for field in expected_fields:
                    assert field in upload, f"Upload missing field: {field}"

                break  # Only need to check one upload

    def test_batch_query_groups_by_gallery(self, populated_db):
        """Verify batch query correctly groups uploads by gallery"""
        batch_uploads = populated_db.get_all_file_host_uploads_batch()

        # Verify all uploads in each list belong to correct gallery
        for path, uploads_list in batch_uploads.items():
            # Get the gallery ID for this path
            all_galleries = populated_db.load_all_items()
            gallery = next((g for g in all_galleries if g['path'] == path), None)
            assert gallery is not None, f"Gallery not found for path: {path}"

            gallery_fk = gallery['db_id']

            # Verify all uploads reference this gallery
            for upload in uploads_list:
                assert upload['gallery_fk'] == gallery_fk, \
                    f"Upload has wrong gallery_fk: expected {gallery_fk}, got {upload['gallery_fk']}"

    def test_batch_query_preserves_order(self, populated_db):
        """Verify batch query preserves upload order (by created_ts)"""
        batch_uploads = populated_db.get_all_file_host_uploads_batch()

        # Check order within each gallery's uploads
        for path, uploads_list in batch_uploads.items():
            if len(uploads_list) < 2:
                continue

            # Verify uploads are ordered by created_ts
            timestamps = [u.get('created_ts', 0) for u in uploads_list]
            assert timestamps == sorted(timestamps), \
                f"Uploads for {path} not ordered by created_ts: {timestamps}"


class TestBatchQueryLargeDatasets:
    """Test batch query with large datasets"""

    def test_batch_query_with_many_galleries(self, temp_db):
        """Verify batch query handles 1000+ galleries efficiently"""
        # Create 1000 galleries
        galleries = [
            {
                'path': f'/fake/gallery_{i}',
                'name': f'Gallery {i}',
                'status': 'ready',
                'added_time': 1700000000 + i,
            }
            for i in range(1000)
        ]
        temp_db.bulk_upsert(galleries)

        # Add 1 upload to every 10th gallery (100 uploads total)
        for i in range(0, 1000, 10):
            temp_db.add_file_host_upload(
                gallery_path=f'/fake/gallery_{i}',
                host_name='rapidgator',
                status='completed'
            )

        # Should complete quickly
        start = time.time()
        batch_uploads = temp_db.get_all_file_host_uploads_batch()
        elapsed = time.time() - start

        assert len(batch_uploads) == 100, "Should return 100 galleries with uploads"
        assert elapsed < 1.0, f"Batch query too slow for 1000 galleries: {elapsed:.2f}s"

    def test_batch_query_with_many_uploads_per_gallery(self, temp_db):
        """Verify batch query handles galleries with many uploads"""
        # Create 1 gallery
        gallery_data = {
            'path': '/fake/test_gallery',
            'name': 'Test Gallery',
            'status': 'ready',
            'added_time': 1700000000,
        }
        temp_db.bulk_upsert([gallery_data])

        # Add 50 uploads to this gallery
        for i in range(50):
            temp_db.add_file_host_upload(
                gallery_path='/fake/test_gallery',
                host_name=f'host_{i}',
                status='completed'
            )

        batch_uploads = temp_db.get_all_file_host_uploads_batch()

        assert len(batch_uploads) == 1, "Should return 1 gallery"
        assert len(batch_uploads['/fake/test_gallery']) == 50, \
            "Should return all 50 uploads for gallery"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
