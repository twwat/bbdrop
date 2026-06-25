"""Tests for get_daily_breakdown to ensure files_deduped column is included.

Regression test for bug where daily breakdown silently returned empty list
because the SELECT query didn't include files_deduped column, but the result
loop tried to access row['files_deduped'], causing KeyError that was caught
and suppressed by a broad except Exception clause.
"""

import pytest
from unittest.mock import patch

from src.utils.metrics_store import MetricsStore


@pytest.fixture
def store(tmp_path):
    """Fresh MetricsStore singleton backed by a temp database."""
    db_path = str(tmp_path / "metrics.db")
    with patch.object(MetricsStore, "_get_db_path", return_value=db_path):
        MetricsStore._instance = None
        s = MetricsStore()
        yield s
        s.close()
        MetricsStore._instance = None


class TestDailyBreakdown:
    def test_daily_breakdown_includes_files_deduped(self, store):
        """Daily breakdown should return non-empty list with correct files_deduped value."""
        # Record a transfer with some deduped files
        store.record_transfer(
            host_name="imx",
            bytes_uploaded=1024 * 1024,
            transfer_time=10.0,
            success=True,
            files_count=5,
        )

        # Record a dedup
        store.record_transfer(
            host_name="imx",
            bytes_uploaded=0,
            transfer_time=0.0,
            success=True,
            files_count=2,
            deduped=True,
            bytes_saved=512 * 1024,
        )

        # Flush to ensure writes to DB
        store.flush()

        # Get daily breakdown for the host
        breakdown = store.get_daily_breakdown("imx", days=7)

        # Should return non-empty list (regression: old code returned empty due to KeyError)
        assert len(breakdown) > 0, "Daily breakdown should return at least one day's data"

        # Find today's entry
        today_entry = None
        for entry in breakdown:
            if entry['date'] is not None:  # Should have a date
                today_entry = entry
                break

        assert today_entry is not None, "Should have at least one daily entry"

        # Verify the structure includes files_deduped (regression: was KeyError before fix)
        assert 'files_deduped' in today_entry, "Entry should include files_deduped key"

        # Verify the values match what we recorded
        # Note: deduped files are also counted in files_uploaded (see _record_dedup logic)
        assert today_entry['files_uploaded'] == 7, "Should have 7 total uploaded (5 normal + 2 deduped)"
        assert today_entry['files_deduped'] == 2, "Should have 2 deduped files"
        assert today_entry['files_failed'] == 0, "Should have 0 failed files"

    def test_daily_breakdown_with_multiple_days(self, store):
        """Daily breakdown should include files_deduped across multiple days."""
        # Record on today
        store.record_transfer(
            host_name="turbo",
            bytes_uploaded=500000,
            transfer_time=5.0,
            success=True,
            files_count=3,
        )

        # Record a dedup
        store.record_transfer(
            host_name="turbo",
            bytes_uploaded=0,
            transfer_time=0.0,
            success=True,
            files_count=1,
            deduped=True,
            bytes_saved=100000,
        )

        store.flush()

        # Get daily breakdown
        breakdown = store.get_daily_breakdown("turbo", days=7)

        # Should have at least one day's data
        assert len(breakdown) > 0

        # All entries should have files_deduped field (not KeyError)
        for entry in breakdown:
            assert 'files_deduped' in entry, f"Entry {entry['date']} missing files_deduped"
            assert 'files_uploaded' in entry, f"Entry {entry['date']} missing files_uploaded"
            assert 'files_failed' in entry, f"Entry {entry['date']} missing files_failed"
