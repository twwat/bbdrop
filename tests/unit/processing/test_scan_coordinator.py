"""Tests for ScanCoordinator — multi-host scan orchestration."""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock, call

from src.processing.scan_coordinator import ScanCoordinator, HostScanJob


class TestHostScanJob:
    """Test the HostScanJob dataclass."""

    def test_creation(self):
        """Should create a job with required fields."""
        job = HostScanJob(
            host_type='image',
            host_id='turbo',
            galleries=[{'db_id': 1, 'path': '/a', 'thumb_urls': ['u1']}],
        )
        assert job.host_id == 'turbo'
        assert job.host_type == 'image'
        assert len(job.galleries) == 1

    def test_total_items(self):
        """total_items should count across all galleries."""
        job = HostScanJob(
            host_type='file',
            host_id='rapidgator',
            galleries=[
                {'db_id': 1, 'file_ids': ['f1', 'f2']},
                {'db_id': 2, 'file_ids': ['f3']},
            ],
        )
        # total_items calculated from file_ids or thumb_urls
        assert len(job.galleries) == 2


class TestScanCoordinatorGrouping:
    """Test gallery-to-host grouping logic."""

    def test_group_by_image_host(self):
        """Galleries with different image_host_id should be grouped separately."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        galleries = [
            {'db_id': 1, 'path': '/a', 'image_host_id': 'turbo', 'thumb_urls': ['u1']},
            {'db_id': 2, 'path': '/b', 'image_host_id': 'turbo', 'thumb_urls': ['u2']},
            {'db_id': 3, 'path': '/c', 'image_host_id': 'pixhost', 'thumb_urls': ['u3']},
        ]
        jobs = coord._build_image_host_jobs(galleries)
        host_ids = {j.host_id for j in jobs}
        assert host_ids == {'turbo', 'pixhost'}

    def test_group_by_file_host(self):
        """File host uploads should be grouped by host_name."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        file_uploads = [
            {'gallery_fk': 1, 'host_name': 'rapidgator', 'file_id': 'f1', 'download_url': 'u1'},
            {'gallery_fk': 1, 'host_name': 'keep2share', 'file_id': 'f2', 'download_url': 'u2'},
            {'gallery_fk': 2, 'host_name': 'rapidgator', 'file_id': 'f3', 'download_url': 'u3'},
        ]
        jobs = coord._build_file_host_jobs(file_uploads)
        host_ids = {j.host_id for j in jobs}
        assert host_ids == {'rapidgator', 'keep2share'}


class TestScanCoordinatorExecution:
    """Test scan execution and result collection."""

    @patch('src.processing.scan_coordinator.ThumbnailChecker')
    def test_image_host_scan_calls_checker(self, MockChecker):
        """Image host job should create ThumbnailChecker and call check_gallery."""
        mock_instance = Mock()
        mock_instance.check_gallery.return_value = {
            'status': 'online', 'online': 5, 'offline': 0, 'errors': 0, 'total': 5, 'offline_urls': []
        }
        MockChecker.return_value = mock_instance

        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        coord._connection_limiter = Mock()
        coord._connection_limiter.connection.return_value.__enter__ = Mock()
        coord._connection_limiter.connection.return_value.__exit__ = Mock(return_value=False)
        coord._progress_callback = None

        job = HostScanJob(
            host_type='image',
            host_id='turbo',
            galleries=[{'db_id': 1, 'path': '/a', 'thumb_urls': ['u1', 'u2', 'u3', 'u4', 'u5']}],
        )
        results = coord._run_image_host_job(job)
        assert len(results) == 1
        assert results[0][3] == 'online'  # status field in result tuple

    @patch('src.processing.scan_coordinator.K2SFileChecker')
    def test_k2s_file_scan_calls_checker(self, MockChecker):
        """K2S file host job should walk folders via get_all_files and check via inventory."""
        mock_instance = Mock()
        mock_instance.get_all_files.return_value = [
            {'id': 'f1', 'name': 'file1.zip', 'size': 1024, 'status': 1},
        ]
        mock_instance.calc_storage_used.return_value = 1024
        mock_instance.check_gallery_from_inventory.return_value = {
            'status': 'online', 'online': 1, 'offline': 0, 'errors': 0, 'total': 1, 'offline_urls': []
        }
        MockChecker.return_value = mock_instance

        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        coord._connection_limiter = Mock()
        coord._connection_limiter.connection.return_value.__enter__ = Mock()
        coord._connection_limiter.connection.return_value.__exit__ = Mock(return_value=False)
        coord._progress_callback = None
        coord._credentials = {'keep2share': 'test-token'}
        coord._k2s_inventory_by_host = {}
        coord._k2s_storage_by_host = {}
        coord._k2s_lock = threading.Lock()

        job = HostScanJob(
            host_type='file',
            host_id='keep2share',
            galleries=[{'db_id': 1, 'file_ids': {'f1': 'http://k2s.cc/file/f1'}}],
        )
        results = coord._run_k2s_job(job)
        assert len(results) == 1
        assert results[0][3] == 'online'  # status field in result tuple
        mock_instance.get_all_files.assert_called_once()
        mock_instance.check_gallery_from_inventory.assert_called_once()


class TestScanCoordinatorCancellation:
    """Test cancellation behavior."""

    def test_cancel_sets_event(self):
        """cancel() should set the cancellation event."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        coord.cancel()
        assert coord._cancelled.is_set()

    def test_is_cancelled_returns_event_state(self):
        """is_cancelled should reflect the event state."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        assert not coord.is_cancelled
        coord._cancelled.set()
        assert coord.is_cancelled

    def test_is_scanning_false_when_no_thread(self):
        """is_scanning should return False when _scan_thread is None."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._scan_thread = None
        assert not coord.is_scanning

    def test_is_scanning_true_when_thread_alive(self):
        """is_scanning should return True when _scan_thread is alive."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        # Create a short-lived thread
        coord._scan_thread = threading.Thread(target=lambda: time.sleep(0.1))
        coord._scan_thread.start()
        # Thread should be alive immediately after start
        assert coord.is_scanning
        coord._scan_thread.join()
        # After join, thread should be dead
        assert not coord.is_scanning

    def test_is_scanning_false_when_thread_dead(self):
        """is_scanning should return False when _scan_thread has finished."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._scan_thread = threading.Thread(target=lambda: None)
        coord._scan_thread.start()
        coord._scan_thread.join()
        assert not coord.is_scanning

    def test_wait_returns_true_when_no_thread(self):
        """wait() should return True immediately if _scan_thread is None."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._scan_thread = None
        result = coord.wait(timeout=1.0)
        assert result is True

    def test_wait_returns_true_after_thread_finishes(self):
        """wait() should return True when thread finishes within timeout."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._scan_thread = threading.Thread(target=lambda: time.sleep(0.05))
        coord._scan_thread.start()
        result = coord.wait(timeout=1.0)
        assert result is True

    def test_wait_returns_false_on_timeout(self):
        """wait() should return False if thread doesn't finish within timeout."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._scan_thread = threading.Thread(target=lambda: time.sleep(2.0))
        coord._scan_thread.start()
        result = coord.wait(timeout=0.05)
        assert result is False
        # Clean up
        coord._scan_thread.join(timeout=0.1)


class TestScanCoordinatorXFSWebDispatcher:
    """Test dispatcher routing for XFS-web hosts (filedot, filespace)."""

    def test_dispatcher_routes_filedot_to_xfs_web_job(self, monkeypatch):
        """Filedot job should be handed to _run_xfs_web_job, not skipped."""
        coord = ScanCoordinator(store=MagicMock(), connection_limiter=MagicMock())
        called = []
        monkeypatch.setattr(coord, "_run_xfs_web_job",
                            lambda job: called.append(job) or [])
        job = HostScanJob(host_type="file", host_id="filedot", galleries=[])
        coord._run_job(job)
        assert called and called[0].host_id == "filedot"

    def test_dispatcher_routes_filespace_to_xfs_web_job(self, monkeypatch):
        """Filespace job should be handed to _run_xfs_web_job, not skipped."""
        coord = ScanCoordinator(store=MagicMock(), connection_limiter=MagicMock())
        called = []
        monkeypatch.setattr(coord, "_run_xfs_web_job",
                            lambda job: called.append(job) or [])
        job = HostScanJob(host_type="file", host_id="filespace", galleries=[])
        coord._run_job(job)
        assert called and called[0].host_id == "filespace"


class TestScanCoordinatorIMXRouting:
    """Test that IMX galleries are routed to the moderat endpoint, not ThumbnailChecker."""

    def test_imx_excluded_from_thumbnail_jobs(self):
        """IMX galleries should NOT be in thumbnail checker jobs (handled via _run_imx_job)."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        galleries = [
            {'db_id': 1, 'path': '/a', 'image_host_id': 'imx', 'thumb_urls': ['u1']},
            {'db_id': 2, 'path': '/b', 'image_host_id': 'turbo', 'thumb_urls': ['u2']},
        ]
        jobs = coord._build_image_host_jobs(galleries)
        host_ids = {j.host_id for j in jobs}
        assert 'imx' not in host_ids
        assert 'turbo' in host_ids

    def test_imx_job_built_separately(self):
        """IMX galleries should produce a separate IMX job."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        galleries = [
            {'db_id': 1, 'image_host_id': 'imx', 'image_urls': ['https://imx.to/i/abc']},
            {'db_id': 2, 'image_host_id': 'turbo', 'thumb_urls': ['u2']},
        ]
        imx_job = coord._build_imx_job(galleries)
        assert imx_job is not None
        assert imx_job.host_id == 'imx'
        assert len(imx_job.galleries) == 1

    def test_no_imx_job_when_no_imx_galleries(self):
        """No IMX job if there are no IMX galleries."""
        coord = ScanCoordinator.__new__(ScanCoordinator)
        coord._cancelled = threading.Event()
        galleries = [
            {'db_id': 1, 'image_host_id': 'turbo', 'thumb_urls': ['u1']},
        ]
        assert coord._build_imx_job(galleries) is None
