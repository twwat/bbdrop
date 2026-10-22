"""Tests for MetricsStore database persistence.

Regression coverage for the files_count plumbing: record_transfer()
accepted a files_count (e.g. 88 images in one gallery upload) and the
in-memory caches counted it, but the DB write path hardcoded 1 file per
transfer — so 'today' and 'all_time' periods (read from the DB) showed
almost nothing while 'session' looked right.
"""

import pytest
from unittest.mock import patch

from src.utils.metrics_store import MetricsStore, PeakSpeedValidator


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


class TestAverageSpeedPeriods:
    """avg_speed for every period is bytes / transfer time over that period.

    Regression: today/all_time avg was a rolling window of this process's
    transfers only, so after one upload in a new session 'avg speed (all
    time)' showed exactly the session value instead of the historical one.
    """

    MB = 1024 * 1024

    def test_all_time_avg_includes_history_after_restart(self, store):
        # History: 100 MB in 100 s (1 MB/s)
        store.record_transfer(host_name="rapidgator", bytes_uploaded=100 * self.MB,
                              transfer_time=100.0, success=True)
        store.flush()

        # Restart: fresh instance on the same DB, empty in-memory caches
        db_path = store._get_db_path()
        store.close()
        MetricsStore._instance = None
        fresh = MetricsStore()
        try:
            emitted = []
            fresh.signals.host_metrics_updated.connect(
                lambda host, m: emitted.append(m))
            # This session: 10 MB in 1 s (10 MB/s)
            fresh.record_transfer(host_name="rapidgator", bytes_uploaded=10 * self.MB,
                                  transfer_time=1.0, success=True)
            m = emitted[-1]
            assert m["session"]["avg_speed"] == pytest.approx(10 * self.MB)
            assert m["all_time"]["avg_speed"] == pytest.approx(110 * self.MB / 101.0)
            assert m["today"]["avg_speed"] == pytest.approx(110 * self.MB / 101.0)
        finally:
            fresh.close()

    def test_session_avg_covers_whole_session(self, store):
        emitted = []
        store.signals.host_metrics_updated.connect(lambda host, m: emitted.append(m))
        # 11 transfers: first is slow and large, would fall out of a last-10 window
        store.record_transfer(host_name="filedot", bytes_uploaded=100 * self.MB,
                              transfer_time=100.0, success=True)
        for _ in range(10):
            store.record_transfer(host_name="filedot", bytes_uploaded=10 * self.MB,
                                  transfer_time=1.0, success=True)
        assert emitted[-1]["session"]["avg_speed"] == pytest.approx(200 * self.MB / 110.0)


class TestImpossiblePeaks:
    """peak_speed must never hold a value at or above the physical-sanity
    backstop (PeakSpeedValidator.MAX_REALISTIC_KBPS).

    Regression: a Feb 2026 migration clamped bogus peaks to exactly the
    backstop instead of clearing them, leaving IMX showing a permanent
    "12,800 MiB/s" all-time peak. And the bytes/time fallback in
    record_transfer skipped the backstop entirely.
    """

    CAP = PeakSpeedValidator.MAX_REALISTIC_KBPS * 1024  # bytes/s

    def _peaks(self, store, host_name):
        conn = store._connect()
        try:
            return [r["peak_speed"] for r in conn.execute(
                "SELECT peak_speed FROM host_metrics WHERE host_name = ? "
                "ORDER BY id", (host_name,))]
        finally:
            conn.close()

    def test_startup_clears_clamped_peaks_keeps_real_ones(self, store):
        conn = store._connect()
        try:
            conn.executemany(
                "INSERT INTO host_metrics (host_name, bytes_uploaded, "
                "total_transfer_time, peak_speed, peak_speed_date, "
                "period_type, period_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("imx", 5169152, 0.09, self.CAP, None, "daily", "2026-02-02"),
                    ("imx", 34600197567, 1619.2, self.CAP, "2026-02-25 18:09:49", "all_time", None),
                    ("imx", 526449611, 22.2, 64365948.35, "2026-09-19 11:54:02", "all_time", None),
                ],
            )
            # Simulate a DB from before this fix: reset not yet run
            conn.execute("DELETE FROM settings_kv WHERE key='peak_speed_clamp_reset_v1'")
        finally:
            conn.close()

        # Restart on the same DB
        store.close()
        MetricsStore._instance = None
        fresh = MetricsStore()
        try:
            assert self._peaks(fresh, "imx") == [0, 0, pytest.approx(64365948.35)]
            all_time = fresh.get_aggregated_metrics("imx", "all_time")
            assert all_time["peak_speed"] == pytest.approx(64365948.35)
            assert all_time["peak_speed_date"] == "2026-09-19 11:54:02"
        finally:
            fresh.close()

    def test_impossible_bytes_over_time_does_not_set_peak(self, store):
        emitted = []
        store.signals.host_metrics_updated.connect(lambda host, m: emitted.append(m))
        # Zero transfer time with no observed peak: bytes/time fallback
        # would read as terabytes per second.
        store.record_transfer(host_name="imx", bytes_uploaded=20 * 1024 ** 3,
                              transfer_time=0.0, success=True, files_count=6)
        store.flush()

        for period in ("session", "today", "all_time"):
            assert emitted[-1][period]["peak_speed"] == 0
        assert self._peaks(store, "imx") == [0, 0]
        # The bytes and files still count
        assert _db_row(store, "imx", "daily")["bytes_uploaded"] == 20 * 1024 ** 3
        assert _db_row(store, "imx", "daily")["files_uploaded"] == 6

    def test_realistic_peak_still_recorded(self, store):
        store.record_transfer(host_name="imx", bytes_uploaded=100 * 1024 * 1024,
                              transfer_time=2.0, success=True)
        store.flush()
        assert self._peaks(store, "imx") == [pytest.approx(50 * 1024 * 1024)] * 2
