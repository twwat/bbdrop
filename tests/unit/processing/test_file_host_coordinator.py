"""
Comprehensive test suite for src/processing/file_host_coordinator.py
Tests FileHostCoordinator with threading, semaphore management, and coordination logic.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch

from src.processing.file_host_coordinator import FileHostCoordinator, get_coordinator


class TestFileHostCoordinatorInit:
    """Test FileHostCoordinator initialization"""

    def test_init_default_limits(self):
        """Test initialization with default limits"""
        coordinator = FileHostCoordinator()
        assert coordinator.global_limit == 3
        assert coordinator.per_host_limit == 2

    def test_init_custom_limits(self):
        """Test initialization with custom limits"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=3)
        assert coordinator.global_limit == 5
        assert coordinator.per_host_limit == 3

    def test_init_statistics_reset(self):
        """Test that statistics are initialized to zero"""
        coordinator = FileHostCoordinator()
        assert coordinator.total_uploads_started == 0
        assert coordinator.total_uploads_completed == 0
        assert coordinator.total_uploads_failed == 0

    def test_init_locks_created(self):
        """Test that all required locks are created"""
        coordinator = FileHostCoordinator()
        assert isinstance(coordinator.host_semaphore_lock, threading.Lock)
        assert isinstance(coordinator.active_uploads_lock, threading.Lock)
        assert isinstance(coordinator.stats_lock, threading.Lock)


class TestFileHostCoordinatorUpdateLimits:
    """Test limit updating functionality"""

    def test_update_global_limit(self):
        """Test updating global limit"""
        coordinator = FileHostCoordinator(global_limit=3)
        coordinator.update_limits(global_limit=5)
        assert coordinator.global_limit == 5

    def test_update_per_host_limit(self):
        """Test updating per-host limit"""
        coordinator = FileHostCoordinator(per_host_limit=2)
        coordinator.update_limits(per_host_limit=4)
        assert coordinator.per_host_limit == 4

    def test_update_both_limits(self):
        """Test updating both limits"""
        coordinator = FileHostCoordinator(global_limit=3, per_host_limit=2)
        coordinator.update_limits(global_limit=6, per_host_limit=4)
        assert coordinator.global_limit == 6
        assert coordinator.per_host_limit == 4

    def test_update_global_limit_creates_new_semaphore(self):
        """Test that global limit update creates new semaphore"""
        coordinator = FileHostCoordinator(global_limit=3)
        old_semaphore = coordinator.global_semaphore
        coordinator.update_limits(global_limit=5)
        assert coordinator.global_semaphore is not old_semaphore


class TestFileHostCoordinatorHostSemaphore:
    """Test host semaphore management"""

    def test_get_host_semaphore_creates_new(self):
        """Test that getting semaphore for new host creates it"""
        coordinator = FileHostCoordinator(per_host_limit=2)
        semaphore = coordinator._get_host_semaphore("rapidgator")
        assert isinstance(semaphore, threading.Semaphore)
        assert "rapidgator" in coordinator.host_semaphores

    def test_get_host_semaphore_returns_existing(self):
        """Test that getting semaphore for existing host returns same instance"""
        coordinator = FileHostCoordinator(per_host_limit=2)
        semaphore1 = coordinator._get_host_semaphore("rapidgator")
        semaphore2 = coordinator._get_host_semaphore("rapidgator")
        assert semaphore1 is semaphore2


class TestFileHostCoordinatorAcquireSlot:
    """Test upload slot acquisition"""

    def test_acquire_slot_basic(self):
        """Test basic slot acquisition"""
        coordinator = FileHostCoordinator(global_limit=3, per_host_limit=2)
        with coordinator.acquire_slot(gallery_id=1, host_name="rapidgator") as acquired:
            assert acquired is True
            assert coordinator.is_upload_active(1, "rapidgator")

    def test_acquire_slot_registers_active_upload(self):
        """Test that acquire_slot registers upload as active"""
        coordinator = FileHostCoordinator()
        with coordinator.acquire_slot(gallery_id=123, host_name="testhost"):
            assert (123, "testhost") in coordinator.active_uploads

    def test_acquire_slot_releases_on_exit(self):
        """Test that slots are released when context exits"""
        coordinator = FileHostCoordinator()
        with coordinator.acquire_slot(gallery_id=1, host_name="rapidgator"):
            assert (1, "rapidgator") in coordinator.active_uploads
        assert (1, "rapidgator") not in coordinator.active_uploads

    def test_acquire_slot_increments_started_counter(self):
        """Test that acquiring slot increments started counter"""
        coordinator = FileHostCoordinator()
        initial_count = coordinator.total_uploads_started
        with coordinator.acquire_slot(gallery_id=1, host_name="rapidgator"):
            pass
        assert coordinator.total_uploads_started == initial_count + 1

    def test_acquire_slot_multiple_hosts(self):
        """Test acquiring slots for different hosts"""
        coordinator = FileHostCoordinator(global_limit=3, per_host_limit=2)
        with coordinator.acquire_slot(gallery_id=1, host_name="rapidgator"):
            with coordinator.acquire_slot(gallery_id=2, host_name="megaupload"):
                assert len(coordinator.active_uploads) == 2

    def test_acquire_slot_timeout_error_message(self):
        """Test that timeout raises proper error message"""
        coordinator = FileHostCoordinator(global_limit=1)
        with coordinator.acquire_slot(1, "host1", timeout=0.05):
            with pytest.raises(TimeoutError):
                with coordinator.acquire_slot(2, "host2", timeout=0.05):
                    pass

    def test_acquire_slot_releases_on_exception(self):
        """Test that slots are released even if exception occurs"""
        coordinator = FileHostCoordinator()
        try:
            with coordinator.acquire_slot(gallery_id=1, host_name="rapidgator"):
                raise ValueError("Test error")
        except ValueError:
            pass
        assert (1, "rapidgator") not in coordinator.active_uploads


class TestFileHostCoordinatorUploadStatus:
    """Test upload status checking"""

    def test_is_upload_active_true(self):
        """Test checking if active upload is active"""
        coordinator = FileHostCoordinator()
        with coordinator.acquire_slot(gallery_id=1, host_name="rapidgator"):
            assert coordinator.is_upload_active(1, "rapidgator") is True

    def test_is_upload_active_false(self):
        """Test checking if inactive upload is inactive"""
        coordinator = FileHostCoordinator()
        assert coordinator.is_upload_active(1, "rapidgator") is False

    def test_get_active_upload_count_total(self):
        """Test getting total active upload count"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=5)
        initial_count = coordinator.get_active_upload_count()
        with coordinator.acquire_slot(1, "host1"):
            with coordinator.acquire_slot(2, "host2"):
                assert coordinator.get_active_upload_count() == initial_count + 2

    def test_get_active_upload_count_by_host(self):
        """Test getting active upload count for specific host"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=5)
        with coordinator.acquire_slot(1, "rapidgator"):
            with coordinator.acquire_slot(2, "rapidgator"):
                with coordinator.acquire_slot(3, "megaupload"):
                    assert coordinator.get_active_upload_count("rapidgator") == 2
                    assert coordinator.get_active_upload_count("megaupload") == 1

    def test_get_active_upload_count_nonexistent_host(self):
        """Test getting count for host with no active uploads"""
        coordinator = FileHostCoordinator()
        assert coordinator.get_active_upload_count("nonexistent") == 0

    def test_get_active_uploads_list(self):
        """Test getting list of all active uploads"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=5)
        with coordinator.acquire_slot(1, "host1"):
            with coordinator.acquire_slot(2, "host2"):
                uploads = coordinator.get_active_uploads()
                assert isinstance(uploads, list)
                assert len(uploads) == 2
                assert (1, "host1") in uploads

    def test_get_active_uploads_empty(self):
        """Test getting list when no uploads are active"""
        coordinator = FileHostCoordinator()
        uploads = coordinator.get_active_uploads()
        assert isinstance(uploads, list)
        assert len(uploads) == 0


class TestFileHostCoordinatorStatistics:
    """Test statistics tracking"""

    def test_record_completion_success(self):
        """Test recording successful completion"""
        coordinator = FileHostCoordinator()
        initial_completed = coordinator.total_uploads_completed
        coordinator.record_completion(success=True)
        assert coordinator.total_uploads_completed == initial_completed + 1
        assert coordinator.total_uploads_failed == 0

    def test_record_completion_failure(self):
        """Test recording failed completion"""
        coordinator = FileHostCoordinator()
        initial_failed = coordinator.total_uploads_failed
        coordinator.record_completion(success=False)
        assert coordinator.total_uploads_failed == initial_failed + 1
        assert coordinator.total_uploads_completed == 0

    def test_record_completion_thread_safe(self):
        """Test that recording completions is thread-safe"""
        coordinator = FileHostCoordinator()
        def record_success():
            for _ in range(10):
                coordinator.record_completion(success=True)
        def record_failure():
            for _ in range(10):
                coordinator.record_completion(success=False)
        threads = [
            threading.Thread(target=record_success),
            threading.Thread(target=record_failure),
            threading.Thread(target=record_success)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert coordinator.total_uploads_completed == 20
        assert coordinator.total_uploads_failed == 10

    def test_get_statistics(self):
        """Test getting statistics dictionary"""
        coordinator = FileHostCoordinator(global_limit=3, per_host_limit=2)
        with coordinator.acquire_slot(1, "host1"):
            coordinator.record_completion(success=True)
            coordinator.record_completion(success=False)
            stats = coordinator.get_statistics()
            assert isinstance(stats, dict)
            assert stats['total_started'] == 1
            assert stats['total_completed'] == 1
            assert stats['total_failed'] == 1

    def test_statistics_persist_across_uploads(self):
        """Test that statistics persist after uploads complete"""
        coordinator = FileHostCoordinator()
        with coordinator.acquire_slot(1, "host1"):
            coordinator.record_completion(success=True)
        with coordinator.acquire_slot(2, "host2"):
            coordinator.record_completion(success=False)
        stats = coordinator.get_statistics()
        assert stats['total_started'] == 2
        assert stats['total_completed'] == 1
        assert stats['total_failed'] == 1


class TestFileHostCoordinatorAvailableSlots:
    """Test available slots calculation"""

    def test_get_available_slots_global(self):
        """Test calculating available global slots"""
        coordinator = FileHostCoordinator(global_limit=3)
        assert coordinator.get_available_slots() == 3
        with coordinator.acquire_slot(1, "host1"):
            assert coordinator.get_available_slots() == 2
        assert coordinator.get_available_slots() == 3

    def test_get_available_slots_per_host(self):
        """Test calculating available per-host slots"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=2)
        assert coordinator.get_available_slots("rapidgator") == 2
        with coordinator.acquire_slot(1, "rapidgator"):
            assert coordinator.get_available_slots("rapidgator") == 1

    def test_get_available_slots_minimum_of_global_and_host(self):
        """Test that available slots is minimum"""
        coordinator = FileHostCoordinator(global_limit=1, per_host_limit=5)
        assert coordinator.get_available_slots("host1") == 1

    def test_get_available_slots_never_negative(self):
        """Test that available slots never goes below zero"""
        coordinator = FileHostCoordinator(global_limit=1, per_host_limit=1)
        with coordinator.acquire_slot(1, "host1"):
            assert coordinator.get_available_slots() == 0


class TestFileHostCoordinatorCanStartUpload:
    """Test upload readiness checking"""

    def test_can_start_upload_with_available_slots(self):
        """Test can_start_upload when slots available"""
        coordinator = FileHostCoordinator(global_limit=3, per_host_limit=2)
        assert coordinator.can_start_upload("rapidgator") is True

    def test_can_start_upload_without_available_slots(self):
        """Test can_start_upload when no slots available"""
        coordinator = FileHostCoordinator(global_limit=1, per_host_limit=1)
        with coordinator.acquire_slot(1, "rapidgator"):
            assert coordinator.can_start_upload("rapidgator") is False

    def test_can_start_upload_respects_global_limit(self):
        """Test can_start_upload respects global limit"""
        coordinator = FileHostCoordinator(global_limit=2, per_host_limit=5)
        with coordinator.acquire_slot(1, "host1"):
            with coordinator.acquire_slot(2, "host2"):
                assert coordinator.can_start_upload("host3") is False

    def test_can_start_upload_respects_per_host_limit(self):
        """Test can_start_upload respects per-host limit"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=1)
        with coordinator.acquire_slot(1, "rapidgator"):
            assert coordinator.can_start_upload("rapidgator") is False


class TestFileHostCoordinatorThreadSafety:
    """Test thread safety of coordinator"""

    def test_concurrent_acquisitions(self):
        """Test concurrent slot acquisitions are thread-safe"""
        coordinator = FileHostCoordinator(global_limit=10, per_host_limit=10)
        active_during_test = []
        def acquire_and_hold():
            with coordinator.acquire_slot(threading.current_thread().ident, "host1"):
                active_during_test.append(1)
                time.sleep(0.01)
        threads = [threading.Thread(target=acquire_and_hold) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(active_during_test) == 10
        assert coordinator.get_active_upload_count() == 0

    def test_concurrent_statistics_updates(self):
        """Test concurrent statistics updates are thread-safe"""
        coordinator = FileHostCoordinator()
        def update_stats():
            for _ in range(50):
                coordinator.record_completion(success=True)
        threads = [threading.Thread(target=update_stats) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert coordinator.total_uploads_completed == 250


class TestFileHostCoordinatorEdgeCases:
    """Test edge cases and error conditions"""

    def test_acquire_slot_same_gallery_different_hosts(self):
        """Test same gallery on different hosts"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=5)
        with coordinator.acquire_slot(gallery_id=1, host_name="host1"):
            with coordinator.acquire_slot(gallery_id=1, host_name="host2"):
                assert coordinator.is_upload_active(1, "host1")
                assert coordinator.is_upload_active(1, "host2")

    def test_update_limits_with_active_uploads(self):
        """Test updating limits while uploads are active"""
        coordinator = FileHostCoordinator(global_limit=3, per_host_limit=2)
        with coordinator.acquire_slot(1, "host1"):
            coordinator.update_limits(global_limit=5, per_host_limit=4)
            assert coordinator.is_upload_active(1, "host1")
            assert coordinator.global_limit == 5


class TestGetCoordinator:
    """Test global coordinator singleton"""

    def test_get_coordinator_returns_instance(self):
        """Test that get_coordinator returns FileHostCoordinator instance"""
        import src.processing.file_host_coordinator as fhc_module
        fhc_module._coordinator = None
        coordinator = get_coordinator()
        assert isinstance(coordinator, FileHostCoordinator)

    def test_get_coordinator_singleton(self):
        """Test that get_coordinator returns same instance"""
        import src.processing.file_host_coordinator as fhc_module
        fhc_module._coordinator = None
        coordinator1 = get_coordinator()
        coordinator2 = get_coordinator()
        assert coordinator1 is coordinator2

    def test_get_coordinator_default_limits(self):
        """Test that get_coordinator creates instance with default limits"""
        import src.processing.file_host_coordinator as fhc_module
        fhc_module._coordinator = None
        coordinator = get_coordinator()
        assert coordinator.global_limit == 3
        assert coordinator.per_host_limit == 2


class TestFileHostCoordinatorIntegration:
    """Integration tests combining multiple features"""

    def test_complete_upload_workflow(self):
        """Test complete upload workflow"""
        coordinator = FileHostCoordinator(global_limit=3, per_host_limit=2)
        with coordinator.acquire_slot(gallery_id=1, host_name="host1"):
            with coordinator.acquire_slot(gallery_id=2, host_name="host2"):
                with coordinator.acquire_slot(gallery_id=3, host_name="host1"):
                    assert coordinator.get_active_upload_count() == 3
                    coordinator.record_completion(success=True)
                    coordinator.record_completion(success=False)
        stats = coordinator.get_statistics()
        assert stats['total_completed'] == 1
        assert stats['total_failed'] == 1

    def test_max_capacity_handling(self):
        """Test handling when at maximum capacity"""
        coordinator = FileHostCoordinator(global_limit=2, per_host_limit=2)
        with coordinator.acquire_slot(1, "host1"):
            with coordinator.acquire_slot(2, "host1"):
                assert coordinator.can_start_upload("host2") is False
                assert coordinator.get_available_slots() == 0

    def test_mixed_host_loads(self):
        """Test with mixed host loads"""
        coordinator = FileHostCoordinator(global_limit=5, per_host_limit=2)
        with coordinator.acquire_slot(1, "host1"):
            with coordinator.acquire_slot(2, "host1"):
                assert not coordinator.can_start_upload("host1")
                assert coordinator.can_start_upload("host2")
                with coordinator.acquire_slot(3, "host2"):
                    with coordinator.acquire_slot(4, "host2"):
                        assert coordinator.can_start_upload("host3")
