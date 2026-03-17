"""Tests for host_registry and metrics key migration."""

import sqlite3
import pytest
from unittest.mock import patch, MagicMock


class TestGetDisplayName:

    def test_image_host_returns_config_name(self):
        from src.core.host_registry import get_display_name, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()  # Force re-init
        # IMX.to is defined in assets/image_hosts/imx.json with name "IMX.to"
        assert get_display_name('imx') == 'IMX.to'

    def test_file_host_returns_config_name(self):
        from src.core.host_registry import get_display_name, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()
        assert get_display_name('keep2share') == 'Keep2Share'

    def test_unknown_host_returns_host_id(self):
        from src.core.host_registry import get_display_name, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()
        assert get_display_name('nonexistent_host') == 'nonexistent_host'

    def test_turbo_returns_full_name(self):
        from src.core.host_registry import get_display_name, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()
        assert get_display_name('turbo') == 'TurboImageHost'

    def test_tezfiles_preserves_casing(self):
        from src.core.host_registry import get_display_name, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()
        assert get_display_name('tezfiles') == 'TezFiles'

    def test_fileboom_preserves_casing(self):
        from src.core.host_registry import get_display_name, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()
        assert get_display_name('fileboom') == 'FileBoom'


class TestGetAllHostIds:

    def test_returns_all_known_hosts(self):
        from src.core.host_registry import get_all_host_ids, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()
        ids = get_all_host_ids()
        # Should include both image and file hosts
        assert 'imx' in ids
        assert 'turbo' in ids
        assert 'rapidgator' in ids
        assert 'keep2share' in ids

    def test_cached_after_first_call(self):
        from src.core.host_registry import get_display_name, _DISPLAY_NAMES
        _DISPLAY_NAMES.clear()
        get_display_name('imx')
        # Should be populated now
        assert len(_DISPLAY_NAMES) > 0
        # Second call shouldn't clear it
        result = get_display_name('imx')
        assert result == 'IMX.to'


class TestMetricsKeyMigration:
    """Test one-time migration of display-name keys to host_id keys."""

    @pytest.fixture
    def dirty_db(self, tmp_path):
        """Create a metrics DB with old display-name keys."""
        db_path = str(tmp_path / "metrics.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE host_metrics (
                id INTEGER PRIMARY KEY,
                host_name TEXT NOT NULL,
                bytes_uploaded INTEGER DEFAULT 0,
                files_uploaded INTEGER DEFAULT 0,
                files_failed INTEGER DEFAULT 0,
                files_deduped INTEGER DEFAULT 0,
                total_transfer_time REAL DEFAULT 0,
                peak_speed REAL DEFAULT 0,
                peak_speed_date TEXT,
                period_type TEXT NOT NULL,
                period_date TEXT,
                created_ts INTEGER DEFAULT 0,
                updated_ts INTEGER DEFAULT 0,
                UNIQUE(host_name, period_type, period_date)
            );
        """)
        # Old display-name keys
        conn.execute(
            "INSERT INTO host_metrics (host_name, bytes_uploaded, files_uploaded, peak_speed, period_type, period_date) VALUES (?, ?, ?, ?, ?, ?)",
            ('IMX.to', 1000, 10, 500.0, 'all_time', None)
        )
        conn.execute(
            "INSERT INTO host_metrics (host_name, bytes_uploaded, files_uploaded, peak_speed, period_type, period_date) VALUES (?, ?, ?, ?, ?, ?)",
            ('Imx', 500, 5, 300.0, 'all_time', None)
        )
        # Correct host_id key
        conn.execute(
            "INSERT INTO host_metrics (host_name, bytes_uploaded, files_uploaded, peak_speed, period_type, period_date) VALUES (?, ?, ?, ?, ?, ?)",
            ('rapidgator', 2000, 20, 100.0, 'all_time', None)
        )
        # Test artifact
        conn.execute(
            "INSERT INTO host_metrics (host_name, bytes_uploaded, files_uploaded, peak_speed, period_type, period_date) VALUES (?, ?, ?, ?, ?, ?)",
            ('Host_0', 100, 1, 50.0, 'all_time', None)
        )
        conn.commit()
        conn.close()
        return db_path

    def test_merges_imx_variants(self, dirty_db):
        from src.utils.metrics_store import _migrate_host_name_keys
        _migrate_host_name_keys(dirty_db)
        conn = sqlite3.connect(dirty_db)
        rows = conn.execute(
            "SELECT host_name, bytes_uploaded, files_uploaded, peak_speed FROM host_metrics WHERE period_type='all_time' AND host_name='imx'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][1] == 1500  # 1000 + 500
        assert rows[0][2] == 15    # 10 + 5
        assert rows[0][3] == 500.0 # max(500, 300)

    def test_deletes_test_artifacts(self, dirty_db):
        from src.utils.metrics_store import _migrate_host_name_keys
        _migrate_host_name_keys(dirty_db)
        conn = sqlite3.connect(dirty_db)
        count = conn.execute("SELECT COUNT(*) FROM host_metrics WHERE host_name LIKE 'Host_%'").fetchone()[0]
        conn.close()
        assert count == 0

    def test_leaves_correct_keys_untouched(self, dirty_db):
        from src.utils.metrics_store import _migrate_host_name_keys
        _migrate_host_name_keys(dirty_db)
        conn = sqlite3.connect(dirty_db)
        rows = conn.execute(
            "SELECT bytes_uploaded FROM host_metrics WHERE host_name='rapidgator' AND period_type='all_time'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == 2000

    def test_skips_if_already_clean(self, dirty_db):
        from src.utils.metrics_store import _migrate_host_name_keys
        _migrate_host_name_keys(dirty_db)
        # Running again should not error or duplicate
        _migrate_host_name_keys(dirty_db)
        conn = sqlite3.connect(dirty_db)
        count = conn.execute("SELECT COUNT(*) FROM host_metrics WHERE host_name='imx' AND period_type='all_time'").fetchone()[0]
        conn.close()
        assert count == 1
