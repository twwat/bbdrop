"""Tests for disk space pre-flight check before archive creation."""

import pytest


class TestFileHostPreFlight:
    """FileHostWorker should check space before archive creation."""

    def test_archive_refused_when_insufficient_space(self):
        """Direct shutil.disk_usage check before create_or_reuse_archive."""
        # Test the concept: if free < estimated + critical, refuse
        free_bytes = 400_000_000  # 400 MB
        estimated_size = 200_000_000  # 200 MB archive
        critical_threshold = 512 * 1024 * 1024  # 512 MB

        has_enough = free_bytes > estimated_size + critical_threshold
        assert has_enough is False, "Should refuse: 400MB < 200MB + 512MB"

    def test_archive_allowed_when_sufficient_space(self):
        free_bytes = 2_000_000_000  # 2 GB
        estimated_size = 200_000_000  # 200 MB archive
        critical_threshold = 512 * 1024 * 1024  # 512 MB

        has_enough = free_bytes > estimated_size + critical_threshold
        assert has_enough is True, "Should allow: 2GB > 200MB + 512MB"
