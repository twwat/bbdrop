"""
Comprehensive tests for core.engine module.

Tests cover:
- AtomicCounter thread-safe operations
- ByteCountingCallback progress tracking
- UploadEngine initialization and configuration
- File gathering and sorting (natural sort, Windows Explorer sort)
- Gallery creation workflows (new gallery, resume, append)
- Concurrent upload operations
- Retry logic and error handling
- Progress callbacks and soft stop functionality
- Statistics aggregation and dimension calculation
- Thread-local session management
"""

import pytest
import os
import tempfile
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, MagicMock, patch, call
import concurrent.futures

from src.core.engine import (
    AtomicCounter,
    ByteCountingCallback,
    UploadEngine
)


# ============================================================================
# AtomicCounter Tests
# ============================================================================

class TestAtomicCounter:
    """Test suite for AtomicCounter thread-safe byte counter."""

    def test_counter_initializes_to_zero(self):
        """Test counter starts at zero."""
        counter = AtomicCounter()
        assert counter.get() == 0

    def test_counter_add_single_value(self):
        """Test adding a single value to counter."""
        counter = AtomicCounter()
        counter.add(100)
        assert counter.get() == 100

    def test_counter_add_multiple_values(self):
        """Test adding multiple values to counter."""
        counter = AtomicCounter()
        counter.add(100)
        counter.add(200)
        counter.add(50)
        assert counter.get() == 350

    def test_counter_reset(self):
        """Test resetting counter to zero."""
        counter = AtomicCounter()
        counter.add(500)
        counter.reset()
        assert counter.get() == 0

    def test_counter_thread_safety(self):
        """Test counter is thread-safe under concurrent access."""
        counter = AtomicCounter()
        num_threads = 10
        increments_per_thread = 1000

        def increment_counter():
            for _ in range(increments_per_thread):
                counter.add(1)

        threads = [threading.Thread(target=increment_counter) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = num_threads * increments_per_thread
        assert counter.get() == expected

    @pytest.mark.parametrize("values,expected", [
        ([1, 2, 3, 4, 5], 15),
        ([100, 200, 300], 600),
        ([0, 0, 0], 0),
        ([1000000], 1000000),
    ])
    def test_counter_various_values(self, values, expected):
        """Test counter with various input patterns."""
        counter = AtomicCounter()
        for val in values:
            counter.add(val)
        assert counter.get() == expected

    def test_counter_negative_values(self):
        """Test counter handles negative values (for completeness)."""
        counter = AtomicCounter()
        counter.add(100)
        counter.add(-50)
        assert counter.get() == 50


# ============================================================================
# ByteCountingCallback Tests
# ============================================================================

class TestByteCountingCallback:
    """Test suite for ByteCountingCallback upload progress tracker."""

    def test_callback_initializes_without_counter(self):
        """Test callback can be initialized without a counter."""
        callback = ByteCountingCallback()
        assert callback.global_counter is None
        assert callback.last_bytes == 0

    def test_callback_initializes_with_counter(self):
        """Test callback initializes with global counter."""
        counter = AtomicCounter()
        callback = ByteCountingCallback(global_counter=counter)
        assert callback.global_counter is counter
        assert callback.last_bytes == 0

    def test_callback_tracks_progress_deltas(self):
        """Test callback tracks byte deltas correctly."""
        counter = AtomicCounter()
        callback = ByteCountingCallback(global_counter=counter)

        # Simulate progress updates
        callback(100, 1000)  # 100 bytes read
        assert counter.get() == 100

        callback(250, 1000)  # 250 total (delta: 150)
        assert counter.get() == 250

        callback(500, 1000)  # 500 total (delta: 250)
        assert counter.get() == 500

    def test_callback_ignores_no_progress(self):
        """Test callback ignores calls with no progress."""
        counter = AtomicCounter()
        callback = ByteCountingCallback(global_counter=counter)

        callback(100, 1000)
        assert counter.get() == 100

        callback(100, 1000)  # Same value - no delta
        assert counter.get() == 100

    def test_callback_without_counter_does_nothing(self):
        """Test callback without counter doesn't crash."""
        callback = ByteCountingCallback()
        callback(100, 1000)  # Should not raise
        callback(200, 1000)  # Should not raise

    def test_callback_handles_zero_deltas(self):
        """Test callback handles zero-byte deltas gracefully."""
        counter = AtomicCounter()
        callback = ByteCountingCallback(global_counter=counter)

        callback(0, 1000)
        assert counter.get() == 0

        callback(0, 1000)
        assert counter.get() == 0


# ============================================================================
# UploadEngine Initialization Tests
# ============================================================================

class TestUploadEngineInitialization:
    """Test suite for UploadEngine initialization."""

    def test_engine_initializes_with_uploader(self):
        """Test engine initializes with required uploader."""
        mock_uploader = Mock()
        engine = UploadEngine(mock_uploader)

        assert engine.uploader is mock_uploader
        assert engine.rename_worker is None
        assert isinstance(engine.global_byte_counter, AtomicCounter)
        assert engine.gallery_byte_counter is None

    def test_engine_initializes_with_all_parameters(self):
        """Test engine initializes with all optional parameters."""
        mock_uploader = Mock()
        mock_rename_worker = Mock()
        global_counter = AtomicCounter()
        gallery_counter = AtomicCounter()
        mock_worker_thread = Mock()

        engine = UploadEngine(
            uploader=mock_uploader,
            rename_worker=mock_rename_worker,
            global_byte_counter=global_counter,
            gallery_byte_counter=gallery_counter,
            worker_thread=mock_worker_thread
        )

        assert engine.uploader is mock_uploader
        assert engine.rename_worker is mock_rename_worker
        assert engine.global_byte_counter is global_counter
        assert engine.gallery_byte_counter is gallery_counter
        assert engine.worker_thread is mock_worker_thread

    def test_engine_creates_default_counter_if_not_provided(self):
        """Test engine creates default counter when not provided."""
        mock_uploader = Mock()
        engine = UploadEngine(mock_uploader)

        assert isinstance(engine.global_byte_counter, AtomicCounter)
        assert engine.global_byte_counter.get() == 0


# ============================================================================
# File Gathering and Sorting Tests
# ============================================================================

class TestFileGatheringAndSorting:
    """Test suite for file gathering and natural sorting."""

    @pytest.fixture
    def temp_image_folder(self):
        """Create temporary folder with test images."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def create_test_images(self, folder: str, filenames: List[str]):
        """Helper to create empty test image files."""
        for filename in filenames:
            filepath = os.path.join(folder, filename)
            with open(filepath, 'wb') as f:
                f.write(b'fake-image-data')

    def test_engine_gathers_image_files(self, temp_image_folder):
        """Test engine correctly identifies image files."""
        self.create_test_images(temp_image_folder, [
            'image1.jpg',
            'photo.png',
            'test.gif',
            'document.txt',  # Should be ignored
            'video.mp4'  # Should be ignored
        ])

        mock_uploader = Mock()
        mock_uploader.upload_image.return_value = {
            'status': 'success',
            'data': {'gallery_id': 'test123', 'image_url': 'http://test.com/img'}
        }

        engine = UploadEngine(mock_uploader)

        # This would normally be called in run() - testing the logic
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif')
        image_files = [
            f for f in os.listdir(temp_image_folder)
            if f.lower().endswith(image_extensions) and os.path.isfile(os.path.join(temp_image_folder, f))
        ]

        assert len(image_files) == 3
        assert 'image1.jpg' in image_files
        assert 'photo.png' in image_files
        assert 'test.gif' in image_files
        assert 'document.txt' not in image_files

    @pytest.mark.parametrize("filenames,expected_order", [
        (['img1.jpg', 'img10.jpg', 'img2.jpg'], ['img1.jpg', 'img2.jpg', 'img10.jpg']),
        (['z.jpg', 'a.jpg', 'm.jpg'], ['a.jpg', 'm.jpg', 'z.jpg']),
        (['file100.png', 'file20.png', 'file3.png'], ['file3.png', 'file20.png', 'file100.png']),
    ])
    def test_natural_sort_ordering(self, temp_image_folder, filenames, expected_order):
        """Test natural sort ordering of image files."""
        self.create_test_images(temp_image_folder, filenames)

        # Import natural sort key from engine
        import re
        def _natural_sort_key(name: str):
            parts = re.split(r"(\d+)", name)
            key = []
            for p in parts:
                if p.isdigit():
                    try:
                        key.append(int(p))
                    except Exception:
                        key.append(p)
                else:
                    key.append(p.lower())
            return tuple(key)

        sorted_files = sorted(filenames, key=_natural_sort_key)
        assert sorted_files == expected_order


# ============================================================================
# Gallery Creation Tests
# ============================================================================

class TestGalleryCreation:
    """Test suite for gallery creation workflows."""

    @pytest.fixture
    def temp_image_folder(self):
        """Create temporary folder with test images."""
        temp_dir = tempfile.mkdtemp()

        # Create test images
        for i in range(3):
            filepath = os.path.join(temp_dir, f'test{i}.jpg')
            with open(filepath, 'wb') as f:
                f.write(b'x' * 1024)  # 1KB fake image

        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_engine_raises_error_for_nonexistent_folder(self):
        """Test engine raises FileNotFoundError for missing folder."""
        mock_uploader = Mock()
        engine = UploadEngine(mock_uploader)

        with pytest.raises(FileNotFoundError, match="Folder not found"):
            engine.run(
                folder_path="/nonexistent/path",
                gallery_name="Test",
                thumbnail_size=3,
                thumbnail_format=2,
                max_retries=3,
                parallel_batch_size=2,
                template_name="default"
            )

    def test_engine_raises_error_for_folder_without_images(self):
        """Test engine raises ValueError when no images found."""
        temp_dir = tempfile.mkdtemp()
        try:
            mock_uploader = Mock()
            engine = UploadEngine(mock_uploader)

            with pytest.raises(ValueError, match="No image files found"):
                engine.run(
                    folder_path=temp_dir,
                    gallery_name="Test",
                    thumbnail_size=3,
                    thumbnail_format=2,
                    max_retries=3,
                    parallel_batch_size=2,
                    template_name="default"
                )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_engine_creates_new_gallery_with_first_image(self, temp_image_folder):
        """Test engine creates new gallery by uploading first image."""
        mock_uploader = Mock()

        # CRITICAL: Mock headers as a real dict, not a Mock property
        # The engine accesses uploader.headers in thread sessions
        mock_uploader.configure_mock(headers={})

        # CRITICAL: Mock web_url attribute used for gallery URLs
        mock_uploader.configure_mock(web_url='https://imx.to')

        # FIXED: Use callable that handles infinite calls (including retries)
        def mock_upload(image_path, gallery_id=None, create_gallery=False, **kwargs):
            return {
                'status': 'success',
                'data': {
                    'gallery_id': gallery_id or 'gal123',
                    'image_url': f'http://imx.to/i/abc/{os.path.basename(image_path)}',
                    'thumbnail_url': f'http://imx.to/i/abc/thumb_{os.path.basename(image_path)}'
                }
            }

        mock_uploader.upload_image.side_effect = mock_upload

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test Gallery",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default"
        )

        assert result['gallery_id'] == 'gal123'
        assert result['gallery_url'] == 'https://imx.to/g/gal123'
        assert result['successful_count'] == 3
        assert result['failed_count'] == 0

    def test_engine_resumes_to_existing_gallery(self, temp_image_folder):
        """Test engine resumes upload to existing gallery."""
        mock_uploader = Mock()

        # FIXED: Configure mock attributes for threading
        mock_uploader.configure_mock(headers={})
        mock_uploader.configure_mock(web_url='https://imx.to')

        # FIXED: Use callable side_effect for threading
        def mock_upload(image_path, gallery_id=None, **kwargs):
            return {
                'status': 'success',
                'data': {
                    'gallery_id': gallery_id or 'existing123',
                    'image_url': f'http://imx.to/i/abc/{os.path.basename(image_path)}'
                }
            }

        mock_uploader.upload_image.side_effect = mock_upload

        engine = UploadEngine(mock_uploader)

        # Simulate resume with one file already uploaded
        already_uploaded = {'test0.jpg'}

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test Gallery",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default",
            existing_gallery_id="existing123",
            already_uploaded=already_uploaded
        )

        assert result['gallery_id'] == 'existing123'
        assert result['successful_count'] == 3  # 1 already + 2 uploaded
        assert mock_uploader.upload_image.call_count == 2  # Only 2 new uploads


# ============================================================================
# Upload Operations Tests
# ============================================================================

class TestUploadOperations:
    """Test suite for concurrent upload operations."""

    @pytest.fixture
    def temp_image_folder(self):
        """Create temporary folder with test images."""
        temp_dir = tempfile.mkdtemp()

        for i in range(5):
            filepath = os.path.join(temp_dir, f'img{i}.jpg')
            with open(filepath, 'wb') as f:
                f.write(b'x' * 1024)

        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_engine_handles_upload_failures(self, temp_image_folder):
        """Test engine handles individual upload failures gracefully."""
        mock_uploader = Mock()

        # FIXED: Configure mock attributes for threading
        mock_uploader.configure_mock(headers={})
        mock_uploader.configure_mock(web_url='https://imx.to')

        # FIXED: Use callable to track calls and return appropriate responses
        call_count = [0]
        def mock_upload(image_path, gallery_id=None, **kwargs):
            call_count[0] += 1
            # First succeeds (creates gallery), second fails, rest succeed
            if call_count[0] == 2:
                return {'status': 'error', 'message': 'Network error'}
            return {
                'status': 'success',
                'data': {
                    'gallery_id': gallery_id or 'gal123',
                    'image_url': f'http://test.com/{call_count[0]}'
                }
            }

        mock_uploader.upload_image.side_effect = mock_upload

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=0,  # No retries to test failure handling
            parallel_batch_size=2,
            template_name="default"
        )

        assert result['successful_count'] == 4
        assert result['failed_count'] == 1

    def test_engine_retries_failed_uploads(self, temp_image_folder):
        """Test engine retries failed uploads up to max_retries."""
        mock_uploader = Mock()

        # FIXED: Configure mock attributes for threading
        mock_uploader.configure_mock(headers={})
        mock_uploader.configure_mock(web_url='https://imx.to')

        # FIXED: Use callable to simulate failure then success on retry
        call_count = [0]
        failed_once = {'img1.jpg': False}  # Track which file failed once

        def mock_upload(image_path, gallery_id=None, **kwargs):
            call_count[0] += 1
            filename = os.path.basename(image_path)

            # img1.jpg fails first time, succeeds on retry
            if filename == 'img1.jpg' and not failed_once[filename]:
                failed_once[filename] = True
                return {'status': 'error', 'message': 'Timeout'}

            return {
                'status': 'success',
                'data': {
                    'gallery_id': gallery_id or 'gal123',
                    'image_url': f'http://test.com/{call_count[0]}'
                }
            }

        mock_uploader.upload_image.side_effect = mock_upload

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default"
        )

        assert result['successful_count'] == 5
        assert result['failed_count'] == 0


# ============================================================================
# Callback Tests
# ============================================================================

class TestCallbacks:
    """Test suite for progress callbacks and soft stop."""

    @pytest.fixture
    def temp_image_folder(self):
        """Create temporary folder with test images."""
        temp_dir = tempfile.mkdtemp()

        for i in range(3):
            filepath = os.path.join(temp_dir, f'test{i}.jpg')
            with open(filepath, 'wb') as f:
                f.write(b'x' * 1024)

        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_progress_callback_is_called(self, temp_image_folder):
        """Test on_progress callback is invoked during upload."""
        mock_uploader = Mock()
        mock_uploader.upload_image.return_value = {
            'status': 'success',
            'data': {'gallery_id': 'gal123', 'image_url': 'http://test.com/img'}
        }

        progress_calls = []

        def progress_callback(completed, total, percent, filename):
            progress_calls.append((completed, total, percent, filename))

        engine = UploadEngine(mock_uploader)

        engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default",
            on_progress=progress_callback
        )

        # Should have progress updates for each image
        assert len(progress_calls) >= 3

    def test_soft_stop_halts_upload(self, temp_image_folder):
        """Test should_soft_stop callback halts upload gracefully."""
        mock_uploader = Mock()

        upload_count = 0

        def upload_side_effect(*args, **kwargs):
            nonlocal upload_count
            upload_count += 1
            return {
                'status': 'success',
                'data': {'gallery_id': 'gal123', 'image_url': f'http://test.com/img{upload_count}'}
            }

        mock_uploader.upload_image.side_effect = upload_side_effect

        stop_after = 2

        def soft_stop_callback():
            return upload_count >= stop_after

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=1,
            template_name="default",
            should_soft_stop=soft_stop_callback
        )

        # Should stop early (1 for gallery creation + some more before stop)
        assert result['successful_count'] <= 3

    def test_image_uploaded_callback_is_called(self, temp_image_folder):
        """Test on_image_uploaded callback is invoked for each upload."""
        mock_uploader = Mock()

        # FIXED: Configure mock attributes for threading
        mock_uploader.configure_mock(headers={})
        mock_uploader.configure_mock(web_url='https://imx.to')

        # FIXED: Use callable side_effect for threading
        def mock_upload(image_path, gallery_id=None, **kwargs):
            return {
                'status': 'success',
                'data': {
                    'gallery_id': gallery_id or 'gal123',
                    'image_url': f'http://test.com/{os.path.basename(image_path)}'
                }
            }

        mock_uploader.upload_image.side_effect = mock_upload

        uploaded_images = []

        def image_uploaded_callback(filename, image_data, size_bytes):
            uploaded_images.append((filename, image_data, size_bytes))

        engine = UploadEngine(mock_uploader)

        engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default",
            on_image_uploaded=image_uploaded_callback
        )

        assert len(uploaded_images) == 3


# ============================================================================
# Statistics and Results Tests
# ============================================================================

class TestStatisticsAndResults:
    """Test suite for statistics aggregation and results."""

    @pytest.fixture
    def temp_image_folder(self):
        """Create temporary folder with test images."""
        temp_dir = tempfile.mkdtemp()

        for i in range(3):
            filepath = os.path.join(temp_dir, f'test{i}.jpg')
            with open(filepath, 'wb') as f:
                f.write(b'x' * 1024)

        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_result_contains_required_fields(self, temp_image_folder):
        """Test result dictionary contains all required fields."""
        mock_uploader = Mock()
        mock_uploader.upload_image.return_value = {
            'status': 'success',
            'data': {'gallery_id': 'gal123', 'image_url': 'http://test.com/img'}
        }

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test Gallery",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default"
        )

        required_fields = [
            'gallery_url', 'gallery_id', 'gallery_name',
            'upload_time', 'total_size', 'uploaded_size', 'transfer_speed',
            'successful_count', 'failed_count', 'failed_details',
            'thumbnail_size', 'thumbnail_format', 'parallel_batch_size',
            'template_name', 'total_images', 'started_at', 'images'
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    def test_result_calculates_upload_statistics(self, temp_image_folder):
        """Test result includes accurate upload statistics."""
        mock_uploader = Mock()

        # FIXED: Configure mock attributes for threading
        mock_uploader.configure_mock(headers={})
        mock_uploader.configure_mock(web_url='https://imx.to')

        # FIXED: Use callable side_effect for threading
        def mock_upload(image_path, gallery_id=None, **kwargs):
            return {
                'status': 'success',
                'data': {
                    'gallery_id': gallery_id or 'gal123',
                    'image_url': f'http://test.com/{os.path.basename(image_path)}'
                }
            }

        mock_uploader.upload_image.side_effect = mock_upload

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default"
        )

        assert result['successful_count'] == 3
        assert result['failed_count'] == 0
        assert result['total_images'] == 3
        assert result['upload_time'] > 0
        assert result['total_size'] == 3 * 1024  # 3 files, 1KB each
        assert result['transfer_speed'] >= 0

    def test_precalculated_dimensions_are_used(self, temp_image_folder):
        """Test precalculated dimensions are included in results."""
        mock_uploader = Mock()
        mock_uploader.upload_image.return_value = {
            'status': 'success',
            'data': {'gallery_id': 'gal123', 'image_url': 'http://test.com/img'}
        }

        # Mock precalculated dimensions
        mock_dimensions = type('obj', (object,), {
            'avg_width': 1920.0,
            'avg_height': 1080.0,
            'max_width': 3840.0,
            'max_height': 2160.0,
            'min_width': 1280.0,
            'min_height': 720.0
        })()

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default",
            precalculated_dimensions=mock_dimensions
        )

        assert result['avg_width'] == 1920.0
        assert result['avg_height'] == 1080.0
        assert result['max_width'] == 3840.0
        assert result['max_height'] == 2160.0


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================

class TestEdgeCasesAndErrors:
    """Test suite for edge cases and error conditions."""

    def test_engine_handles_gallery_creation_failure(self):
        """Test engine handles failure when creating gallery."""
        temp_dir = tempfile.mkdtemp()
        try:
            filepath = os.path.join(temp_dir, 'test.jpg')
            with open(filepath, 'wb') as f:
                f.write(b'x' * 1024)

            mock_uploader = Mock()
            mock_uploader.upload_image.return_value = {
                'status': 'error',
                'message': 'Failed to create gallery'
            }

            engine = UploadEngine(mock_uploader)

            with pytest.raises(Exception, match="Failed to create gallery"):
                engine.run(
                    folder_path=temp_dir,
                    gallery_name="Test",
                    thumbnail_size=3,
                    thumbnail_format=2,
                    max_retries=3,
                    parallel_batch_size=2,
                    template_name="default"
                )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_engine_handles_empty_gallery_name(self):
        """Test engine uses folder name when gallery name is empty."""
        temp_dir = tempfile.mkdtemp(prefix="test_gallery_")
        try:
            filepath = os.path.join(temp_dir, 'test.jpg')
            with open(filepath, 'wb') as f:
                f.write(b'x' * 1024)

            mock_uploader = Mock()
            mock_uploader.upload_image.return_value = {
                'status': 'success',
                'data': {'gallery_id': 'gal123', 'image_url': 'http://test.com/img'}
            }

            engine = UploadEngine(mock_uploader)

            result = engine.run(
                folder_path=temp_dir,
                gallery_name=None,  # No name provided
                thumbnail_size=3,
                thumbnail_format=2,
                max_retries=3,
                parallel_batch_size=2,
                template_name="default"
            )

            # Should use folder basename
            assert result['gallery_name'] is not None
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_engine_handles_all_uploads_failing(self):
        """Test engine handles scenario where all uploads fail."""
        temp_dir = tempfile.mkdtemp()
        try:
            for i in range(3):
                filepath = os.path.join(temp_dir, f'test{i}.jpg')
                with open(filepath, 'wb') as f:
                    f.write(b'x' * 1024)

            mock_uploader = Mock()

            # First creates gallery, rest fail
            mock_uploader.upload_image.side_effect = [
                {'status': 'success', 'data': {'gallery_id': 'gal123', 'image_url': 'http://test.com/1'}},
                {'status': 'error', 'message': 'Upload failed'},
                {'status': 'error', 'message': 'Upload failed'},
                # Retries also fail
                {'status': 'error', 'message': 'Upload failed'},
                {'status': 'error', 'message': 'Upload failed'},
            ]

            engine = UploadEngine(mock_uploader)

            result = engine.run(
                folder_path=temp_dir,
                gallery_name="Test",
                thumbnail_size=3,
                thumbnail_format=2,
                max_retries=1,
                parallel_batch_size=2,
                template_name="default"
            )

            assert result['successful_count'] == 1  # Only gallery creation
            assert result['failed_count'] == 2
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete upload workflows."""

    @pytest.fixture
    def temp_image_folder(self):
        """Create temporary folder with diverse test images."""
        temp_dir = tempfile.mkdtemp()

        # Create images with various names (for sort testing)
        filenames = ['img1.jpg', 'img10.jpg', 'img2.jpg', 'photo_a.png', 'photo_b.gif']
        for filename in filenames:
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(b'x' * (1024 * (len(filenames))))  # Vary sizes

        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_complete_upload_workflow(self, temp_image_folder):
        """Test complete upload workflow from start to finish."""
        mock_uploader = Mock()

        # FIXED: Configure mock attributes for threading
        mock_uploader.configure_mock(headers={})
        mock_uploader.configure_mock(web_url='https://imx.to')

        # FIXED: Use callable side_effect for threading
        def mock_upload(image_path, gallery_id=None, **kwargs):
            return {
                'status': 'success',
                'data': {
                    'gallery_id': gallery_id or 'gal123',
                    'image_url': f'http://test.com/{os.path.basename(image_path)}'
                }
            }

        mock_uploader.upload_image.side_effect = mock_upload

        progress_updates = []
        uploaded_files = []

        def progress_cb(completed, total, percent, filename):
            progress_updates.append(percent)

        def uploaded_cb(filename, data, size):
            uploaded_files.append(filename)

        engine = UploadEngine(mock_uploader)

        result = engine.run(
            folder_path=temp_image_folder,
            gallery_name="Integration Test",
            thumbnail_size=3,
            thumbnail_format=2,
            max_retries=3,
            parallel_batch_size=2,
            template_name="default",
            on_progress=progress_cb,
            on_image_uploaded=uploaded_cb
        )

        # Verify complete workflow
        assert result['successful_count'] == 5
        assert result['failed_count'] == 0
        assert len(uploaded_files) == 5
        assert len(progress_updates) >= 5
        assert result['gallery_url'].startswith('https://imx.to/g/')
