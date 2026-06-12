"""Tests for MetricsStore database persistence.

Regression coverage for the files_count plumbing: record_transfer()
accepted a files_count (e.g. 88 images in one gallery upload) and the
in-memory caches counted it, but the DB write path hardcoded 1 file per
transfer — so 'today' and 'all_time' periods (read from the DB) showed
almost nothing while 'session' looked right.
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


def _db_row(store, host_name, period_type):
    """Aggregate like get_aggregated_metrics does — all_time rows don't
    upsert-merge (NULL period_date is distinct in SQLite uniques), so the
    canonical read is a SUM across rows."""
    conn = store._connect()
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(files_uploaded), 0) AS files_uploaded, "
            "COALESCE(SUM(files_failed), 0) AS files_failed, "
            "COALESCE(SUM(files_deduped), 0) AS files_deduped, "
            "COALESCE(SUM(bytes_uploaded), 0) AS bytes_uploaded "
            "FROM host_metrics WHERE host_name = ? AND period_type = ?",
            (host_name, period_type),
        ).fetchone()
    finally:
        conn.close()


class TestFilesCountPersistence:
    def test_success_persists_files_count(self, store):
        store.record_transfer(
            host_name="imx",
            bytes_uploaded=1024 * 1024,
            transfer_time=10.0,
            success=True,
            files_count=88,
        )
        store.flush()

        for period in ("daily", "all_time"):
            row = _db_row(store, "imx", period)
            assert row is not None
            assert row["files_uploaded"] == 88
            assert row["files_failed"] == 0

    def test_failure_persists_files_count_as_failed(self, store):
        store.record_transfer(
            host_name="imx",
            bytes_uploaded=0,
            transfer_time=5.0,
            success=False,
            files_count=12,
        )
        store.flush()

        row = _db_row(store, "imx", "all_time")
        assert row["files_uploaded"] == 0
        assert row["files_failed"] == 12

    def test_dedup_persists_files_count(self, store):
        store.record_transfer(
            host_name="filedot",
            bytes_uploaded=0,
            transfer_time=0.0,
            success=True,
            files_count=3,
            deduped=True,
            bytes_saved=500,
        )
        store.flush()

        row = _db_row(store, "filedot", "all_time")
        assert row["files_uploaded"] == 3
        assert row["files_deduped"] == 3

    def test_db_matches_session_cache(self, store):
        """DB counts must agree with the in-memory session cache."""
        for n in (69, 93, 77):
            store.record_transfer(
                host_name="imx",
                bytes_uploaded=n * 1000,
                transfer_time=15.0,
                success=True,
                files_count=n,
            )
        store.flush()

        session = store.get_aggregated_metrics("imx", "session")
        row = _db_row(store, "imx", "all_time")
        assert session["files_uploaded"] == 69 + 93 + 77
        assert row["files_uploaded"] == session["files_uploaded"]
