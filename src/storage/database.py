"""
SQLite-backed storage for uploader internal state.

Responsibilities:
- Initialize database in the central data dir (e.g., ~/.bbdrop/bbdrop.db)
- Provide CRUD for galleries and images used by the queue
- Migrate legacy QSettings queue to SQLite on first use
- Keep operations short and safe for concurrent readers with WAL

Note: All heavy work should be triggered from worker/manager threads, not GUI.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json

from src.utils.logger import log
from src.core.constants import HOST_FAMILY_PRIORITY


def _safe_json_loads(raw: str | None, fallback):
    """Parse JSON with fallback on corrupt data. Logs a warning on failure."""
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        log(f"Corrupt JSON in database, using fallback: {e}", level="warning", category="database")
        return fallback


_LOW_DISK_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB


# Access central data dir path from shared helper
from src.utils.paths import get_central_store_base_path


def _get_db_path() -> str:
    base_dir = get_central_store_base_path()
    return os.path.join(base_dir, "bbdrop.db")


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path, timeout=5, isolation_level=None)  # autocommit by default
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")

    return conn


# Module-level set to track which database paths have been initialized.
# This prevents repeated schema introspection (~20 SQL statements) on every method call.
# Thread-safe because set operations are atomic in CPython (GIL protected).
_schema_initialized_dbs: set[str] = set()


class _ConnectionContext:
    """Context manager that properly closes sqlite3 connections.

    Note: sqlite3.Connection.__exit__ only commits/rollbacks transactions,
    it does NOT close the connection. This context manager ensures proper cleanup.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> sqlite3.Connection:
        self.conn = _connect(self.db_path)
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
        return False


_SCHEMA_VERSION = 14  # Bump this when adding new migrations


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure database schema is created and migrations are run.

    Uses a stored schema version to skip migration checks on startup
    when the database is already up to date.
    """
    # Get database path from connection to track initialization
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]

    # Early return if already initialized this process
    if db_path in _schema_initialized_dbs:
        return

    # Create core schema first (without tab_name initially)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS galleries (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            name TEXT,
            status TEXT NOT NULL CHECK (status IN ('validating','scanning','ready','queued','uploading','paused','incomplete','completed','failed','scan_failed','upload_failed')),
            added_ts INTEGER NOT NULL,
            finished_ts INTEGER,
            template TEXT,
            total_images INTEGER DEFAULT 0,
            uploaded_images INTEGER DEFAULT 0,
            total_size INTEGER DEFAULT 0,
            scan_complete INTEGER DEFAULT 0,
            uploaded_bytes INTEGER DEFAULT 0,
            final_kibps REAL DEFAULT 0.0,
            gallery_id TEXT,
            gallery_url TEXT,
            insertion_order INTEGER DEFAULT 0,
            failed_files TEXT,
            media_type TEXT DEFAULT 'image',
            download_links TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS galleries_status_idx ON galleries(status);
        CREATE INDEX IF NOT EXISTS galleries_added_idx ON galleries(added_ts DESC);
        CREATE INDEX IF NOT EXISTS galleries_order_idx ON galleries(insertion_order);
        CREATE INDEX IF NOT EXISTS galleries_path_idx ON galleries(path);

        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY,
            gallery_fk INTEGER NOT NULL REFERENCES galleries(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            size_bytes INTEGER DEFAULT 0,
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            uploaded_ts INTEGER,
            url TEXT,
            thumb_url TEXT,
            UNIQUE(gallery_fk, filename)
        );
        CREATE INDEX IF NOT EXISTS images_gallery_idx ON images(gallery_fk);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value_text TEXT
        );

        CREATE TABLE IF NOT EXISTS unnamed_galleries (
            gallery_id TEXT PRIMARY KEY,
            intended_name TEXT NOT NULL,
            discovered_ts INTEGER DEFAULT (strftime('%s', 'now'))
        );
        CREATE INDEX IF NOT EXISTS unnamed_galleries_ts_idx ON unnamed_galleries(discovered_ts DESC);

        CREATE TABLE IF NOT EXISTS tabs (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            tab_type TEXT NOT NULL CHECK (tab_type IN ('system','user')),
            display_order INTEGER NOT NULL DEFAULT 0,
            color_hint TEXT,
            created_ts INTEGER DEFAULT (strftime('%s', 'now')),
            updated_ts INTEGER DEFAULT (strftime('%s', 'now')),
            is_active INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS tabs_display_order_idx ON tabs(display_order ASC, created_ts ASC);
        CREATE INDEX IF NOT EXISTS tabs_type_idx ON tabs(tab_type);
        CREATE INDEX IF NOT EXISTS tabs_active_idx ON tabs(is_active, display_order ASC);

        CREATE TABLE IF NOT EXISTS file_host_uploads (
            id INTEGER PRIMARY KEY,
            gallery_fk INTEGER NOT NULL REFERENCES galleries(id) ON DELETE CASCADE,
            host_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending','uploading','completed','failed','cancelled')),

            -- Upload tracking
            zip_path TEXT,
            started_ts INTEGER,
            finished_ts INTEGER,
            uploaded_bytes INTEGER DEFAULT 0,
            total_bytes INTEGER DEFAULT 0,

            -- Results
            download_url TEXT,
            file_id TEXT,
            file_name TEXT,
            error_message TEXT,

            -- Metadata
            raw_response TEXT,
            retry_count INTEGER DEFAULT 0,
            created_ts INTEGER DEFAULT (strftime('%s', 'now')),

            UNIQUE(gallery_fk, host_name)
        );
        CREATE INDEX IF NOT EXISTS file_host_uploads_gallery_idx ON file_host_uploads(gallery_fk);
        CREATE INDEX IF NOT EXISTS file_host_uploads_status_idx ON file_host_uploads(status);
        CREATE INDEX IF NOT EXISTS file_host_uploads_host_idx ON file_host_uploads(host_name);
        CREATE INDEX IF NOT EXISTS file_host_uploads_host_status_idx ON file_host_uploads(host_name, status);
        """
    )
    # Check stored schema version — skip migrations if already current
    cur = conn.execute("SELECT value_text FROM settings WHERE key = 'schema_version'")
    row = cur.fetchone()
    stored_version = int(row[0]) if row else 0

    if stored_version < _SCHEMA_VERSION:
        _run_migrations(conn)
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value_text) VALUES('schema_version', ?)",
            (str(_SCHEMA_VERSION),)
        )

    # Mark this database as initialized to skip future calls within this process
    _schema_initialized_dbs.add(db_path)


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run database migrations to add new columns/features."""
    try:
        # Fetch column lists ONCE for each table (avoid repeated PRAGMA calls)
        gallery_columns = {col[1] for col in conn.execute("PRAGMA table_info(galleries)").fetchall()}
        fh_columns = {col[1] for col in conn.execute("PRAGMA table_info(file_host_uploads)").fetchall()}

        # Migration 1: Add failed_files column if it doesn't exist
        if 'failed_files' not in gallery_columns:
            conn.execute("ALTER TABLE galleries ADD COLUMN failed_files TEXT")
            gallery_columns.add('failed_files')
            log("Added failed_files column", level="info", category="database")

        # Migration 2: Add tab_name column if it doesn't exist
        if 'tab_name' not in gallery_columns:
            conn.execute("ALTER TABLE galleries ADD COLUMN tab_name TEXT DEFAULT 'Main'")
            gallery_columns.add('tab_name')
            conn.execute("CREATE INDEX IF NOT EXISTS galleries_tab_idx ON galleries(tab_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS galleries_tab_status_idx ON galleries(tab_name, status)")
            log("Added tab_name column and indexes", level="info", category="database")

        # Migration 3: Move unnamed galleries from config file to database
        _migrate_unnamed_galleries_to_db(conn)

        # Migration 4: Replace tab_name with tab_id for referential integrity
        if 'tab_name' in gallery_columns and 'tab_id' not in gallery_columns:
            # Add tab_id column
            conn.execute("ALTER TABLE galleries ADD COLUMN tab_id INTEGER")
            gallery_columns.add('tab_id')

            # Get all tab names and their IDs
            cursor = conn.execute("SELECT id, name FROM tabs")
            tab_name_to_id = {name: id for id, name in cursor.fetchall()}

            # Update tab_id based on existing tab_name
            for tab_name, tab_id in tab_name_to_id.items():
                conn.execute(
                    "UPDATE galleries SET tab_id = ? WHERE tab_name = ?",
                    (tab_id, tab_name)
                )

            # Set default tab_id for any galleries without a valid tab assignment
            main_tab_id = tab_name_to_id.get('Main', 1)  # Fallback to ID 1 if Main not found
            conn.execute(
                "UPDATE galleries SET tab_id = ? WHERE tab_id IS NULL",
                (main_tab_id,)
            )

            # Add indexes for tab_id
            conn.execute("CREATE INDEX IF NOT EXISTS galleries_tab_id_idx ON galleries(tab_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS galleries_tab_id_status_idx ON galleries(tab_id, status)")

            # Note: We keep tab_name column for now for backwards compatibility
            # but tab_id becomes the primary reference
            log("Migrated to tab_id-based references", level="info", category="database")

        # Migration 4: Initialize default tabs
        _initialize_default_tabs(conn)

        # Migration 5: Add custom fields columns
        # Migration: Add dimension columns for storing calculated values
        dimension_columns = [
            ('avg_width', 'REAL DEFAULT 0.0'),
            ('avg_height', 'REAL DEFAULT 0.0'),
            ('max_width', 'REAL DEFAULT 0.0'),
            ('max_height', 'REAL DEFAULT 0.0'),
            ('min_width', 'REAL DEFAULT 0.0'),
            ('min_height', 'REAL DEFAULT 0.0')
        ]
        added_dim_cols = []
        for col_name, col_def in dimension_columns:
            if col_name not in gallery_columns:
                conn.execute(f"ALTER TABLE galleries ADD COLUMN {col_name} {col_def}")
                gallery_columns.add(col_name)
                added_dim_cols.append(col_name)
        if added_dim_cols:
            log(f"Added dimension columns: {', '.join(added_dim_cols)}", level="debug", category="database")

        added_custom_cols = []
        for custom_field in ['custom1', 'custom2', 'custom3', 'custom4']:
            if custom_field not in gallery_columns:
                conn.execute(f"ALTER TABLE galleries ADD COLUMN {custom_field} TEXT")
                gallery_columns.add(custom_field)
                added_custom_cols.append(custom_field)
        if added_custom_cols:
            log(f"Added custom fields: {', '.join(added_custom_cols)}", level="debug", category="database")

        # Add external program result fields (ext1-4)
        added_ext_cols = []
        for ext_field in ['ext1', 'ext2', 'ext3', 'ext4']:
            if ext_field not in gallery_columns:
                conn.execute(f"ALTER TABLE galleries ADD COLUMN {ext_field} TEXT")
                gallery_columns.add(ext_field)
                added_ext_cols.append(ext_field)
        if added_ext_cols:
            log(f"Added extension fields: {', '.join(added_ext_cols)}", level="debug", category="database")

        # Migration 6: Add IMX status tracking columns
        if 'image_host_id' not in gallery_columns:
            conn.execute("ALTER TABLE galleries ADD COLUMN image_host_id TEXT DEFAULT 'imx'")
            gallery_columns.add('image_host_id')
            log("Added image_host_id column", level="info", category="database")

        if 'imx_status' not in gallery_columns:
            conn.execute("ALTER TABLE galleries ADD COLUMN imx_status TEXT")
            gallery_columns.add('imx_status')
            log("Added imx_status column", level="info", category="database")

        if 'imx_status_checked' not in gallery_columns:
            conn.execute("ALTER TABLE galleries ADD COLUMN imx_status_checked INTEGER")
            gallery_columns.add('imx_status_checked')
            log("Added imx_status_checked column", level="info", category="database")

        # Migration: Add cover photo columns
        added_cover_cols = []
        for cover_col, cover_def in [
            ('cover_source_path', 'TEXT'),
            ('cover_host_id', 'TEXT'),
            ('cover_status', 'TEXT'),
            ('cover_result', 'TEXT'),
        ]:
            if cover_col not in gallery_columns:
                conn.execute(f"ALTER TABLE galleries ADD COLUMN {cover_col} {cover_def}")
                gallery_columns.add(cover_col)
                added_cover_cols.append(cover_col)
        if added_cover_cols:
            log("Added cover columns", level="debug", category="database")

        # Migration to version 11: add media_type column
        if "media_type" not in gallery_columns:
            conn.execute(
                "ALTER TABLE galleries ADD COLUMN media_type TEXT DEFAULT 'image'"
            )
            gallery_columns.add("media_type")
            log("Migration: added media_type column to galleries", level="info", category="database")

        # Migration: add download_links column for manual video download links
        if "download_links" not in gallery_columns:
            conn.execute(
                "ALTER TABLE galleries ADD COLUMN download_links TEXT DEFAULT ''"
            )
            gallery_columns.add("download_links")
            log("Migration: added download_links column to galleries", level="info", category="database")

        # Migration: Add part_number column to file_host_uploads for split archives
        if 'part_number' not in fh_columns:
            conn.execute("ALTER TABLE file_host_uploads ADD COLUMN part_number INTEGER DEFAULT 0")
            # Drop old unique constraint and create new one with part_number
            # SQLite doesn't support DROP CONSTRAINT, so we recreate via index
            # The UNIQUE constraint in CREATE TABLE can't be altered, but INSERT OR REPLACE
            # uses the unique index. We create a new unique index that includes part_number.
            # The old UNIQUE(gallery_fk, host_name) is baked into the table definition,
            # but we can work around it by using INSERT with explicit conflict handling.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS file_host_uploads_gallery_host_part_idx "
                "ON file_host_uploads(gallery_fk, host_name, part_number)"
            )
            log("Added part_number column and gallery_host_part index", level="info", category="database")

        # Migration: Add md5_hash, file_size, deduped columns to file_host_uploads
        if 'md5_hash' not in fh_columns:
            conn.execute("ALTER TABLE file_host_uploads ADD COLUMN md5_hash TEXT")
            conn.execute("ALTER TABLE file_host_uploads ADD COLUMN file_size INTEGER")
            conn.execute("ALTER TABLE file_host_uploads ADD COLUMN deduped INTEGER DEFAULT 0")
            log("Added md5_hash, file_size, deduped columns to file_host_uploads", level="info", category="database")

        # Migration to version 12: rebuild galleries table to update CHECK constraint
        # SQLite can't ALTER CHECK constraints, so we recreate the table.
        # The old constraint was missing 'scan_failed' and 'upload_failed', causing
        # video items to fail upsert and disappear on restart.
        try:
            old_check = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='galleries'"
            ).fetchone()
            if old_check and 'scan_failed' not in (old_check[0] or ''):
                conn.executescript("""
                    ALTER TABLE galleries RENAME TO galleries_old;

                    CREATE TABLE galleries (
                        id INTEGER PRIMARY KEY,
                        path TEXT NOT NULL UNIQUE,
                        name TEXT,
                        status TEXT NOT NULL CHECK (status IN ('validating','scanning','ready','queued','uploading','paused','incomplete','completed','failed','scan_failed','upload_failed')),
                        added_ts INTEGER NOT NULL,
                        finished_ts INTEGER,
                        template TEXT,
                        total_images INTEGER DEFAULT 0,
                        uploaded_images INTEGER DEFAULT 0,
                        total_size INTEGER DEFAULT 0,
                        scan_complete INTEGER DEFAULT 0,
                        uploaded_bytes INTEGER DEFAULT 0,
                        final_kibps REAL DEFAULT 0.0,
                        gallery_id TEXT,
                        gallery_url TEXT,
                        insertion_order INTEGER DEFAULT 0,
                        failed_files TEXT,
                        media_type TEXT DEFAULT 'image',
                        download_links TEXT DEFAULT '',
                        tab_name TEXT DEFAULT 'Main',
                        tab_id INTEGER,
                        custom1 TEXT DEFAULT '',
                        custom2 TEXT DEFAULT '',
                        custom3 TEXT DEFAULT '',
                        custom4 TEXT DEFAULT '',
                        ext1 TEXT DEFAULT '',
                        ext2 TEXT DEFAULT '',
                        ext3 TEXT DEFAULT '',
                        ext4 TEXT DEFAULT '',
                        imx_status TEXT,
                        imx_status_checked INTEGER,
                        image_host_id TEXT DEFAULT 'imx',
                        cover_source_path TEXT,
                        cover_host_id TEXT,
                        cover_status TEXT,
                        cover_result TEXT
                    );

                    INSERT INTO galleries SELECT * FROM galleries_old;
                    DROP TABLE galleries_old;

                    CREATE INDEX IF NOT EXISTS galleries_status_idx ON galleries(status);
                    CREATE INDEX IF NOT EXISTS galleries_path_idx ON galleries(path);
                    CREATE INDEX IF NOT EXISTS galleries_tab_status_idx ON galleries(tab_id, status);
                """)
                log("Migration 12: rebuilt galleries table with updated CHECK constraint", level="info", category="database")
        except Exception as e:
            log(f"Migration 12 (CHECK constraint rebuild) failed: {e}", level="warning", category="database")

        # Migration: Add host_scan_results table for multi-host link scanner
        conn.execute("""
            CREATE TABLE IF NOT EXISTS host_scan_results (
                id INTEGER PRIMARY KEY,
                gallery_fk INTEGER NOT NULL REFERENCES galleries(id) ON DELETE CASCADE,
                host_type TEXT NOT NULL CHECK (host_type IN ('image', 'file')),
                host_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('online', 'offline', 'partial', 'error', 'unknown')),
                online_count INTEGER NOT NULL DEFAULT 0,
                total_count INTEGER NOT NULL DEFAULT 0,
                checked_ts INTEGER NOT NULL,
                detail_json TEXT,
                UNIQUE(gallery_fk, host_type, host_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS scan_results_gallery_idx ON host_scan_results(gallery_fk)")
        conn.execute("CREATE INDEX IF NOT EXISTS scan_results_host_idx ON host_scan_results(host_type, host_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS scan_results_status_idx ON host_scan_results(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS scan_results_checked_idx ON host_scan_results(checked_ts)")

        # Migration to version 14: K2S family dedup support on file_host_uploads.
        # Adds two nullable/defaulted columns and extends the status CHECK
        # constraint to accept 'blocked'. Rebuilds the table because SQLite
        # cannot ALTER a CHECK constraint in place (same pattern as the v12
        # galleries rebuild above).
        fh_columns = {col[1] for col in conn.execute("PRAGMA table_info(file_host_uploads)").fetchall()}

        if 'blocked_by_upload_id' not in fh_columns:
            conn.execute("ALTER TABLE file_host_uploads ADD COLUMN blocked_by_upload_id INTEGER")
            fh_columns.add('blocked_by_upload_id')
            log("Added blocked_by_upload_id column to file_host_uploads",
                level="info", category="database")

        if 'dedup_only' not in fh_columns:
            conn.execute("ALTER TABLE file_host_uploads ADD COLUMN dedup_only INTEGER DEFAULT 0")
            fh_columns.add('dedup_only')
            log("Added dedup_only column to file_host_uploads",
                level="info", category="database")

        # Rebuild the table to widen the status CHECK constraint to include 'blocked'.
        # One-shot: we detect whether the current table definition already mentions 'blocked'
        # and skip the rebuild if so.
        try:
            fh_sql_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='file_host_uploads'"
            ).fetchone()
            if fh_sql_row and "'blocked'" not in (fh_sql_row[0] or ''):
                conn.executescript("""
                    DROP TABLE IF EXISTS file_host_uploads_old;

                    ALTER TABLE file_host_uploads RENAME TO file_host_uploads_old;

                    CREATE TABLE file_host_uploads (
                        id INTEGER PRIMARY KEY,
                        gallery_fk INTEGER NOT NULL REFERENCES galleries(id) ON DELETE CASCADE,
                        host_name TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('pending','uploading','completed','failed','cancelled','blocked')),
                        zip_path TEXT,
                        started_ts INTEGER,
                        finished_ts INTEGER,
                        uploaded_bytes INTEGER DEFAULT 0,
                        total_bytes INTEGER DEFAULT 0,
                        download_url TEXT,
                        file_id TEXT,
                        file_name TEXT,
                        error_message TEXT,
                        raw_response TEXT,
                        retry_count INTEGER DEFAULT 0,
                        created_ts INTEGER DEFAULT (strftime('%s', 'now')),
                        part_number INTEGER DEFAULT 0,
                        md5_hash TEXT,
                        file_size INTEGER,
                        deduped INTEGER DEFAULT 0,
                        blocked_by_upload_id INTEGER,
                        dedup_only INTEGER DEFAULT 0,
                        UNIQUE(gallery_fk, host_name, part_number)
                    );

                    INSERT INTO file_host_uploads
                        (id, gallery_fk, host_name, status, zip_path, started_ts, finished_ts,
                         uploaded_bytes, total_bytes, download_url, file_id, file_name,
                         error_message, raw_response, retry_count, created_ts, part_number,
                         md5_hash, file_size, deduped, blocked_by_upload_id, dedup_only)
                    SELECT
                        id, gallery_fk, host_name, status, zip_path, started_ts, finished_ts,
                        uploaded_bytes, total_bytes, download_url, file_id, file_name,
                        error_message, raw_response, retry_count, created_ts, part_number,
                        md5_hash, file_size, deduped, blocked_by_upload_id, dedup_only
                    FROM file_host_uploads_old;

                    DROP TABLE file_host_uploads_old;

                    CREATE INDEX IF NOT EXISTS file_host_uploads_gallery_idx ON file_host_uploads(gallery_fk);
                    CREATE INDEX IF NOT EXISTS file_host_uploads_status_idx ON file_host_uploads(status);
                    CREATE INDEX IF NOT EXISTS file_host_uploads_host_idx ON file_host_uploads(host_name);
                    CREATE INDEX IF NOT EXISTS file_host_uploads_host_status_idx ON file_host_uploads(host_name, status);
                """)
                log("Migration 14: rebuilt file_host_uploads with widened status CHECK",
                    level="info", category="database")
        except Exception as e:
            log(f"Migration 14 (file_host_uploads CHECK rebuild) failed: {e}",
                level="warning", category="database")

    except Exception as e:
        log(f"Warning: Migration failed: {e}", level="warning", category="database")
        # Continue anyway - the app should still work


def _initialize_default_tabs(conn: sqlite3.Connection) -> None:
    """Initialize default system tabs (one-time migration)."""
    try:
        # Check if we've already initialized default tabs
        cursor = conn.execute("SELECT COUNT(*) FROM tabs WHERE tab_type = 'system'")
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            # Already initialized
            return
            
        # Default system tabs with proper ordering
        default_tabs = [
            ('Main', 'system', 0, None),
        ]

        # Insert default tabs
        for name, tab_type, display_order, color_hint in default_tabs:
            conn.execute(
                "INSERT OR IGNORE INTO tabs (name, tab_type, display_order, color_hint) VALUES (?, ?, ?, ?)",
                (name, tab_type, display_order, color_hint)
            )

        log(f"Initialized {len(default_tabs)} default system tabs", level="info", category="database")

    except Exception as e:
        log(f"Could not initialize default tabs: {e}", level="warning", category="database")
        # Continue anyway - not critical for app function


def _migrate_unnamed_galleries_to_db(conn: sqlite3.Connection) -> None:
    """Migrate unnamed galleries from config file to database (one-time migration)."""
    try:
        # Check if we've already migrated
        cursor = conn.execute("SELECT COUNT(*) FROM unnamed_galleries")
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            # Already migrated
            return
            
        # Try to read from config file
        import configparser
        import os
        
        # Use the same config path logic as the original function
        from src.utils.paths import get_config_path
        config_file = get_config_path()
        
        if not os.path.exists(config_file):
            return  # No config file, nothing to migrate
            
        config = configparser.ConfigParser()
        config.read(config_file, encoding='utf-8')
        
        if 'UNNAMED_GALLERIES' not in config:
            return  # No unnamed galleries section
            
        unnamed_galleries = dict(config['UNNAMED_GALLERIES'])
        if not unnamed_galleries:
            return  # Empty section
            
        log(f"Migrating {len(unnamed_galleries)} unnamed galleries from config file to database...", level="info", category="database")

        # Insert all unnamed galleries into database
        for gallery_id, intended_name in unnamed_galleries.items():
            conn.execute(
                "INSERT OR REPLACE INTO unnamed_galleries (gallery_id, intended_name) VALUES (?, ?)",
                (gallery_id, intended_name)
            )

        log(f"+ Migrated {len(unnamed_galleries)} unnamed galleries to database", level="info", category="database")

        # Optional: Remove from config file after successful migration
        # (Commented out for safety - users can manually clean up)
        # if 'UNNAMED_GALLERIES' in config:
        #     config.remove_section('UNNAMED_GALLERIES')
        #     with open(config_file, 'w') as f:
        #         config.write(f)

    except Exception as e:
        log(f"Could not migrate unnamed galleries: {e}", level="warning", category="database")
        # Continue anyway - not critical for app function


class QueueStore:
    """Storage facade for queue state in SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or _get_db_path()
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # Initialize schema once
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
        # Single writer background pool for non-blocking persistence
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="queue-store")

    # ------------------------------ Migration ------------------------------
    def _is_migrated(self, conn: sqlite3.Connection) -> bool:
        cur = conn.execute("SELECT value_text FROM settings WHERE key = ?", ("queue_migrated_v1",))
        row = cur.fetchone()
        return bool(row and str(row[0]) == "1")

    def _mark_migrated(self, conn: sqlite3.Connection) -> None:
        conn.execute("INSERT OR REPLACE INTO settings(key, value_text) VALUES(?, ?)", ("queue_migrated_v1", "1"))

    def migrate_from_qsettings_if_needed(self, qsettings: Any) -> None:
        """One-time migration from existing QSettings queue list to SQLite.

        qsettings is expected to be a QSettings instance scoped to the old queue,
        providing .value("queue_items", []) as a list of dicts.
        """
        try:
            with _ConnectionContext(self.db_path) as conn:
                _ensure_schema(conn)
                if self._is_migrated(conn):
                    return
                legacy = qsettings.value("queue_items", []) if qsettings else []
                if not legacy:
                    self._mark_migrated(conn)
                    return
                try:
                    for item in legacy:
                        self._upsert_gallery_row(conn, item)
                        # Persist uploaded_files and uploaded_images_data if present
                        uploaded_files = item.get('uploaded_files', []) or []
                        uploaded_images_data = item.get('uploaded_images_data', []) or []
                        # Map fname -> data for convenient URL extraction
                        data_map = {}
                        for tup in uploaded_images_data:
                            try:
                                fname, data = tup
                                data_map[fname] = data or {}
                            except Exception:
                                continue
                        # Insert filenames (and urls if available)
                        cur = conn.execute("SELECT id FROM galleries WHERE path = ?", (item.get('path', ''),))
                        row = cur.fetchone()
                        if not row:
                            continue
                        g_id = int(row[0])
                        for fname in uploaded_files:
                            d = data_map.get(fname, {})
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO images(gallery_fk, filename, size_bytes, width, height, uploaded_ts, url, thumb_url)
                                VALUES(?,?,?,?,?,?,?,?)
                                """,
                                (
                                    g_id,
                                    fname,
                                    int(d.get('size_bytes', 0) or 0),
                                    int(d.get('width', 0) or 0),
                                    int(d.get('height', 0) or 0),
                                    None,
                                    d.get('image_url') or d.get('url') or "",
                                    d.get('thumb_url') or "",
                                ),
                            )
                    self._mark_migrated(conn)
                except Exception:
                    raise
        except Exception:
            # Best-effort migration; do not block app startup
            pass

    # ----------------------------- CRUD helpers ----------------------------
    def _upsert_gallery_row(self, conn: sqlite3.Connection, item: Dict[str, Any]) -> None:
        # Normalize names
        path = item.get('path', '')
        name = item.get('name')
        status = item.get('status', 'ready')
        added_ts = int((item.get('added_time') or 0) or 0)
        finished_ts = int((item.get('finished_time') or 0) or 0) or None
        template = item.get('template_name')
        total_images = int(item.get('total_images', 0) or 0)
        uploaded_images = int(item.get('uploaded_images', 0) or 0)
        total_size = int(item.get('total_size', 0) or 0)
        scan_complete = 1 if bool(item.get('scan_complete', False)) else 0
        uploaded_bytes = int(item.get('uploaded_bytes', 0) or 0)
        final_kibps = float(item.get('final_kibps', 0.0) or 0.0)
        gallery_id = item.get('gallery_id')
        gallery_url = item.get('gallery_url')
        db_id = item.get('db_id')  # Predicted database ID
        insertion_order = int(item.get('insertion_order', 0) or 0)
        failed_files = json.dumps(item.get('failed_files', []))
        tab_name = item.get('tab_name', 'Main')
        custom1 = item.get('custom1', '')
        custom2 = item.get('custom2', '')
        custom3 = item.get('custom3', '')
        custom4 = item.get('custom4', '')
        ext1 = item.get('ext1', '')
        ext2 = item.get('ext2', '')
        ext3 = item.get('ext3', '')
        ext4 = item.get('ext4', '')

        # Extract dimension values
        avg_width = float(item.get('avg_width', 0.0) or 0.0)
        avg_height = float(item.get('avg_height', 0.0) or 0.0)
        max_width = float(item.get('max_width', 0.0) or 0.0)
        max_height = float(item.get('max_height', 0.0) or 0.0)
        min_width = float(item.get('min_width', 0.0) or 0.0)
        min_height = float(item.get('min_height', 0.0) or 0.0)
        
        # Get tab_id for the tab_name
        cursor = conn.execute("SELECT id FROM tabs WHERE name = ? AND is_active = 1", (tab_name,))
        row = cursor.fetchone()
        tab_id = row[0] if row else None
        
        # If tab doesn't exist, default to Main tab
        if tab_id is None:
            cursor = conn.execute("SELECT id FROM tabs WHERE name = 'Main' AND is_active = 1")
            row = cursor.fetchone()
            tab_id = row[0] if row else 1  # Fallback to ID 1
            tab_name = 'Main'


        # Build SQL dynamically based on existing columns
        cursor = conn.execute("PRAGMA table_info(galleries)")
        existing_columns = {column[1] for column in cursor.fetchall()}

        # Base columns that always exist
        columns = ['path', 'name', 'status', 'added_ts', 'finished_ts', 'template', 'total_images', 'uploaded_images',
                   'total_size', 'scan_complete', 'uploaded_bytes', 'final_kibps', 'gallery_id', 'gallery_url',
                   'insertion_order', 'failed_files', 'tab_name']
        values = [path, name, status, added_ts, finished_ts, template, total_images, uploaded_images,
                  total_size, scan_complete, uploaded_bytes, final_kibps, gallery_id, gallery_url,
                  insertion_order, failed_files, tab_name]

        # If db_id is provided (predicted), insert with explicit ID
        if db_id is not None:
            columns.insert(0, 'id')
            values.insert(0, db_id)

        # Extract IMX status values
        imx_status = item.get('imx_status', '')
        imx_status_checked = item.get('imx_status_checked')
        if imx_status_checked is not None:
            imx_status_checked = int(imx_status_checked)

        # Optional columns - add if they exist in schema
        optional_fields = {
            'tab_id': tab_id,
            'custom1': custom1,
            'custom2': custom2,
            'custom3': custom3,
            'custom4': custom4,
            'ext1': ext1,
            'ext2': ext2,
            'ext3': ext3,
            'ext4': ext4,
            'avg_width': avg_width,
            'avg_height': avg_height,
            'max_width': max_width,
            'max_height': max_height,
            'min_width': min_width,
            'min_height': min_height,
            'imx_status': imx_status,
            'imx_status_checked': imx_status_checked,
            'image_host_id': item.get('image_host_id', 'imx'),
            'media_type': item.get('media_type', 'image'),
            'download_links': item.get('download_links', ''),
            'cover_source_path': item.get('cover_source_path'),
            'cover_host_id': item.get('cover_host_id'),
            'cover_status': item.get('cover_status', 'none'),
            'cover_result': json.dumps(item['cover_result']) if item.get('cover_result') is not None else None,
        }

        for col_name, col_value in optional_fields.items():
            if col_name in existing_columns:
                columns.append(col_name)
                values.append(col_value)

        # Build SQL statement
        columns_str = ', '.join(columns)
        placeholders = ','.join(['?'] * len(columns))
        update_pairs = ','.join([f"{col}=excluded.{col}" for col in columns if col not in ('path', 'id')])

        sql = f"""
            INSERT INTO galleries({columns_str})
            VALUES({placeholders})
            ON CONFLICT(path) DO UPDATE SET {update_pairs}
        """

        conn.execute(sql, tuple(values))

    def bulk_upsert(self, items: Iterable[Dict[str, Any]]) -> None:
        items_list = list(items)  # Convert to list to avoid consuming iterator

        # Check disk space before writing
        try:
            usage = shutil.disk_usage(os.path.dirname(self.db_path))
            if usage.free < _LOW_DISK_THRESHOLD_BYTES:
                log(
                    f"Low disk space warning: {usage.free // (1024 * 1024)}MB free "
                    f"at {self.db_path} — database writes may fail silently",
                    level="warning", category="database",
                )
        except OSError:
            pass  # Can't check — proceed anyway

        try:
            with _ConnectionContext(self.db_path) as conn:
                _ensure_schema(conn)
                failures = []
                try:
                    for it in items_list:
                        try:
                            self._upsert_gallery_row(conn, it)
                            # Optionally persist per-image resume info when provided
                            uploaded_files = it.get('uploaded_files') or []
                            uploaded_images_data = it.get('uploaded_images_data') or []
                            if uploaded_files:
                                # Lookup gallery id for images insertion
                                cur = conn.execute("SELECT id FROM galleries WHERE path = ?", (it.get('path', ''),))
                                row = cur.fetchone()
                                if not row:
                                    continue
                                g_id = int(row[0])
                                data_map = {}
                                for tup in uploaded_images_data:
                                    try:
                                        fname, data = tup
                                        data_map[fname] = data or {}
                                    except Exception:
                                        continue
                                for fname in uploaded_files:
                                    d = data_map.get(fname, {})
                                    conn.execute(
                                        """
                                        INSERT OR IGNORE INTO images(gallery_fk, filename, size_bytes, width, height, uploaded_ts, url, thumb_url)
                                        VALUES(?,?,?,?,?,?,?,?)
                                        """,
                                        (
                                            g_id,
                                            fname,
                                            int(d.get('size_bytes', 0) or 0),
                                            int(d.get('width', 0) or 0),
                                            int(d.get('height', 0) or 0),
                                            None,
                                            d.get('image_url') or d.get('url') or "",
                                            d.get('thumb_url') or "",
                                        ),
                                    )
                        except Exception as e:
                            path = it.get('path', 'unknown')
                            log(f"Upsert failed for '{path}': {e}",
                                level="error", category="database")
                            failures.append(path)
                            continue
                    if failures:
                        log(f"Bulk upsert: {len(failures)}/{len(items_list)} items failed", level="warning", category="database")
                except Exception as tx_error:
                    log(f"Transaction failed: {tx_error}", level="error", category="database")
                    raise
        except Exception as e:
            log(f"bulk_upsert failed: {e}", level="error", category="database")

    def bulk_upsert_async(self, items: Iterable[Dict[str, Any]]) -> None:
        # Snapshot to avoid mutation while persisting
        items_list = [dict(it) for it in items]

        def _on_done(future):
            try:
                future.result()
            except Exception as e:
                log(f"Async bulk_upsert failed: {e}",
                    level="error", category="database")

        future = self._executor.submit(self.bulk_upsert, items_list)
        future.add_done_callback(_on_done)

    def load_all_items(self) -> List[Dict[str, Any]]:
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Query with full current schema - NO JOIN for 100x speedup (image_files not used)
            cur = conn.execute(
                """
                SELECT
                    g.id, g.path, g.name, g.status, g.added_ts, g.finished_ts, g.template,
                    g.total_images, g.uploaded_images, g.total_size, g.scan_complete,
                    g.uploaded_bytes, g.final_kibps, g.gallery_id, g.gallery_url,
                    g.insertion_order, g.failed_files, g.tab_name, g.tab_id,
                    g.custom1, g.custom2, g.custom3, g.custom4,
                    g.ext1, g.ext2, g.ext3, g.ext4,
                    g.imx_status, g.imx_status_checked, g.image_host_id,
                    g.media_type, g.download_links,
                    g.cover_source_path, g.cover_host_id, g.cover_status, g.cover_result
                FROM galleries g
                ORDER BY g.insertion_order ASC, g.added_ts ASC
                """
            )

            rows = cur.fetchall()
            items: List[Dict[str, Any]] = []
            for r in rows:
                # Optimized schema: 29 columns (removed image_files GROUP_CONCAT for 100x speedup)
                item: Dict[str, Any] = {
                    'db_id': int(r[0]),  # Database primary key
                    'path': r[1],
                    'name': r[2],
                    'status': r[3],
                    'added_time': int(r[4] or 0),
                    'finished_time': int(r[5] or 0) or None,
                    'template_name': r[6],
                    'total_images': int(r[7] or 0),
                    'uploaded_images': int(r[8] or 0),
                    'total_size': int(r[9] or 0),
                    'scan_complete': bool(r[10] or 0),
                    'uploaded_bytes': int(r[11] or 0),
                    'final_kibps': float(r[12] or 0.0),
                    'gallery_id': r[13] or "",
                    'gallery_url': r[14] or "",
                    'insertion_order': int(r[15] or 0),
                    'failed_files': _safe_json_loads(r[16], []),
                    'tab_name': r[17] or 'Main',
                    'tab_id': int(r[18] or 1),
                    'custom1': r[19] or '',
                    'custom2': r[20] or '',
                    'custom3': r[21] or '',
                    'custom4': r[22] or '',
                    'ext1': r[23] or '',
                    'ext2': r[24] or '',
                    'ext3': r[25] or '',
                    'ext4': r[26] or '',
                    'imx_status': r[27] or '',
                    'imx_status_checked': int(r[28]) if r[28] else None,
                    'image_host_id': r[29] or 'imx',
                    'media_type': r[30] or 'image',
                    'download_links': r[31] or '',
                    'cover_source_path': r[32] or None,
                    'cover_host_id': r[33] or None,
                    'cover_status': r[34] or 'none',
                    'cover_result': _safe_json_loads(r[35], None),
                    'uploaded_files': [],  # Load separately when needed, not in gallery list query
                }
                items.append(item)
            return items

    def get_max_gallery_id(self) -> int:
        """Return the highest gallery id in the database, or 0 if empty."""
        try:
            with _ConnectionContext(self.db_path) as conn:
                _ensure_schema(conn)
                cur = conn.execute("SELECT MAX(id) FROM galleries")
                row = cur.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception:
            return 0

    def delete_by_status(self, statuses: Iterable[str]) -> int:
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            sql = "DELETE FROM galleries WHERE status IN (%s)" % ",".join(["?"] * len(list(statuses)))
            cur = conn.execute(sql, tuple(statuses))
            return cur.rowcount if hasattr(cur, 'rowcount') else 0

    def delete_by_paths(self, paths: Iterable[str]) -> int:
        paths = list(paths)
        if not paths:
            return 0
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            sql = "DELETE FROM galleries WHERE path IN (%s)" % ",".join(["?"] * len(paths))
            cur = conn.execute(sql, tuple(paths))
            return cur.rowcount if hasattr(cur, 'rowcount') else 0

    def update_insertion_orders(self, ordered_paths: List[str]) -> None:
        if not ordered_paths:
            return
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            try:
                for idx, path in enumerate(ordered_paths, 1):
                    conn.execute("UPDATE galleries SET insertion_order = ? WHERE path = ?", (idx, path))
            except Exception:
                raise

    def clear_all(self) -> None:
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            conn.execute("DELETE FROM images")
            conn.execute("DELETE FROM galleries")
            conn.execute("DELETE FROM settings WHERE key = 'queue_migrated_v1'")

    # Unnamed Galleries Database Methods
    def get_unnamed_galleries(self) -> Dict[str, str]:
        """Get all unnamed galleries from database (much faster than config file)."""
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute("SELECT gallery_id, intended_name FROM unnamed_galleries ORDER BY discovered_ts DESC")
            return dict(cursor.fetchall())

    def add_unnamed_gallery(self, gallery_id: str, intended_name: str) -> None:
        """Add an unnamed gallery to the database."""
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            conn.execute(
                "INSERT OR REPLACE INTO unnamed_galleries (gallery_id, intended_name) VALUES (?, ?)",
                (gallery_id, intended_name)
            )

    def remove_unnamed_gallery(self, gallery_id: str) -> bool:
        """Remove an unnamed gallery from the database. Returns True if removed."""
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute("DELETE FROM unnamed_galleries WHERE gallery_id = ?", (gallery_id,))
            return cursor.rowcount > 0

    def clear_unnamed_galleries(self) -> int:
        """Clear all unnamed galleries. Returns count of removed items."""
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute("DELETE FROM unnamed_galleries")
            return cursor.rowcount if hasattr(cursor, 'rowcount') else 0

    # Tab Management Methods
    def get_all_tabs(self) -> List[Dict[str, Any]]:
        """Get all tabs ordered by display_order. Returns list of tab dictionaries."""
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute("""
                SELECT id, name, tab_type, display_order, color_hint, created_ts, updated_ts, is_active
                FROM tabs 
                WHERE is_active = 1 
                ORDER BY display_order ASC, created_ts ASC
            """)
            
            tabs = []
            for row in cursor.fetchall():
                tabs.append({
                    'id': row[0],
                    'name': row[1],
                    'tab_type': row[2],
                    'display_order': row[3],
                    'color_hint': row[4],
                    'created_ts': row[5],
                    'updated_ts': row[6],
                    'is_active': bool(row[7]),
                })
            return tabs

    def get_tab_gallery_counts(self) -> Dict[str, int]:
        """Get gallery counts for each tab. Optimized for fast lookups with single query.
        
        Returns: Dict mapping tab_name -> gallery_count
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            
            # Single optimized query using LEFT JOIN - much faster than UNION
            cursor = conn.execute("""
                SELECT
                    t.name as tab_name,
                    COUNT(g.path) as gallery_count
                FROM tabs t
                LEFT JOIN galleries g ON t.name = COALESCE(g.tab_name, 'Main')
                WHERE t.is_active = 1
                GROUP BY t.name, t.display_order
                ORDER BY t.display_order ASC, t.name ASC
            """)
            
            # Convert to dictionary
            counts = {}
            for row in cursor.fetchall():
                tab_name, count = row[0], row[1]
                counts[tab_name] = count
            
            # Handle edge case: if no tabs exist yet, ensure Main tab is included
            if not counts:
                counts['Main'] = 0
                
            return counts

    def load_items_by_tab(self, tab_name: str) -> List[Dict[str, Any]]:
        """Load galleries filtered by tab name. Uses tab_id for fast filtering.
        
        Args:
            tab_name: Name of the tab to filter by
            
        Returns: List of gallery items belonging to the specified tab
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            
            # Get tab_id for the given tab_name
            cursor = conn.execute("SELECT id FROM tabs WHERE name = ? AND is_active = 1", (tab_name,))
            row = cursor.fetchone()
            if not row:
                return []  # Tab doesn't exist, return empty list
            
            tab_id = row[0]
            
            # Check if failed_files and tab_id columns exist
            cursor = conn.execute("PRAGMA table_info(galleries)")
            columns = [column[1] for column in cursor.fetchall()]
            has_failed_files = 'failed_files' in columns
            has_tab_id = 'tab_id' in columns
            
            # Build optimized query WITHOUT JOIN (image_files not used by GUI)
            if has_failed_files:
                # New schema with failed_files column
                if has_tab_id:
                    # Use tab_id for precise filtering - NO JOIN for 100x speedup
                    cur = conn.execute(
                        """
                        SELECT
                            g.id, g.path, g.name, g.status, g.added_ts, g.finished_ts, g.template,
                            g.total_images, g.uploaded_images, g.total_size, g.scan_complete,
                            g.uploaded_bytes, g.final_kibps, g.gallery_id, g.gallery_url,
                            g.insertion_order, g.failed_files, g.tab_name,
                            g.custom1, g.custom2, g.custom3, g.custom4,
                            g.imx_status, g.imx_status_checked, g.image_host_id
                        FROM galleries g
                        WHERE IFNULL(g.tab_id, 1) = ?
                        ORDER BY g.insertion_order ASC, g.added_ts ASC
                        """,
                        (tab_id,)
                    )
                else:
                    # Fallback to tab_name filtering - NO JOIN for 100x speedup
                    cur = conn.execute(
                        """
                        SELECT
                            g.id, g.path, g.name, g.status, g.added_ts, g.finished_ts, g.template,
                            g.total_images, g.uploaded_images, g.total_size, g.scan_complete,
                            g.uploaded_bytes, g.final_kibps, g.gallery_id, g.gallery_url,
                            g.insertion_order, g.failed_files, g.tab_name,
                            g.custom1, g.custom2, g.custom3, g.custom4,
                            g.imx_status, g.imx_status_checked, g.image_host_id
                        FROM galleries g
                        WHERE IFNULL(g.tab_name, 'Main') = ?
                        ORDER BY g.insertion_order ASC, g.added_ts ASC
                        """,
                        (tab_name,)
                    )
            else:
                # Old schema without failed_files column
                if has_tab_id:
                    # Use tab_id for precise filtering - NO JOIN for 100x speedup
                    cur = conn.execute(
                        """
                        SELECT
                            g.id, g.path, g.name, g.status, g.added_ts, g.finished_ts, g.template,
                            g.total_images, g.uploaded_images, g.total_size, g.scan_complete,
                            g.uploaded_bytes, g.final_kibps, g.gallery_id, g.gallery_url,
                            g.insertion_order
                        FROM galleries g
                        WHERE IFNULL(g.tab_id, 1) = ?
                        ORDER BY g.insertion_order ASC, g.added_ts ASC
                        """,
                        (tab_id,)
                    )
                else:
                    # Fallback to tab_name filtering - NO JOIN for 100x speedup
                    cur = conn.execute(
                        """
                        SELECT
                            g.id, g.path, g.name, g.status, g.added_ts, g.finished_ts, g.template,
                            g.total_images, g.uploaded_images, g.total_size, g.scan_complete,
                            g.uploaded_bytes, g.final_kibps, g.gallery_id, g.gallery_url,
                            g.insertion_order,
                            g.custom1, g.custom2, g.custom3, g.custom4
                        FROM galleries g
                        WHERE IFNULL(g.tab_name, 'Main') = ?
                        ORDER BY g.insertion_order ASC, g.added_ts ASC
                        """,
                        (tab_name,)
                    )
            
            rows = cur.fetchall()
            items: List[Dict[str, Any]] = []
            for r in rows:
                if has_failed_files:
                    # New schema - 24 columns (id at index 0, custom1-4 at 18-21, imx_status at 22-23)
                    item: Dict[str, Any] = {
                        'path': r[1],
                        'name': r[2],
                        'status': r[3],
                        'added_time': int(r[4] or 0),
                        'finished_time': int(r[5] or 0) or None,
                        'template_name': r[6],
                        'total_images': int(r[7] or 0),
                        'uploaded_images': int(r[8] or 0),
                        'total_size': int(r[9] or 0),
                        'scan_complete': bool(r[10] or 0),
                        'uploaded_bytes': int(r[11] or 0),
                        'final_kibps': float(r[12] or 0.0),
                        'gallery_id': r[13] or "",
                        'gallery_url': r[14] or "",
                        'insertion_order': int(r[15] or 0),
                        'failed_files': _safe_json_loads(r[16], []),
                        'tab_name': r[17] or 'Main',
                        'custom1': r[18] or '',
                        'custom2': r[19] or '',
                        'custom3': r[20] or '',
                        'custom4': r[21] or '',
                        'imx_status': r[22] or '',
                        'imx_status_checked': int(r[23]) if r[23] else None,
                        'image_host_id': r[24] or 'imx',
                        'uploaded_files': [],  # Load separately when needed for speed
                    }
                else:
                    # Old schema without failed_files - now only 14 columns (removed image_files)
                    item = {
                        'path': r[1],
                        'name': r[2],
                        'status': r[3],
                        'added_time': int(r[4] or 0),
                        'finished_time': int(r[5] or 0) or None,
                        'template_name': r[6],
                        'total_images': int(r[7] or 0),
                        'uploaded_images': int(r[8] or 0),
                        'total_size': int(r[9] or 0),
                        'scan_complete': bool(r[10] or 0),
                        'uploaded_bytes': int(r[11] or 0),
                        'final_kibps': float(r[12] or 0.0),
                        'gallery_id': r[13] or "",
                        'gallery_url': r[14] or "",
                        'insertion_order': int(r[15] or 0),
                        'failed_files': [],  # Default empty list for old schema
                        'tab_name': tab_name,  # Use the filtered tab name
                        'custom1': '',  # Not available in old schema
                        'custom2': '',
                        'custom3': '',
                        'custom4': '',
                        'uploaded_files': [],  # Load separately when needed for speed
                    }
                
                items.append(item)
            return items

    def create_tab(self, name: str, color_hint: Optional[str] = None, display_order: Optional[int] = None) -> int:
        """Create a new user tab.
        
        Args:
            name: Tab name (must be unique)
            color_hint: Optional hex color code (e.g., '#FF5733')
            display_order: Order position (default: auto-calculated)
            
        Returns: Tab ID of created tab
        
        Raises:
            sqlite3.IntegrityError: If tab name already exists
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            
            try:
                # Auto-calculate display_order if not provided
                if display_order is None:
                    cursor = conn.execute("SELECT MAX(display_order) FROM tabs WHERE tab_type = 'user'")
                    max_order = cursor.fetchone()[0] or 0
                    display_order = max_order + 10  # Leave room for reordering
                
                # Insert new tab (always user type for public API)
                cursor = conn.execute(
                    "INSERT INTO tabs (name, tab_type, display_order, color_hint) VALUES (?, 'user', ?, ?)",
                    (name, display_order, color_hint)
                )
                return cursor.lastrowid or 0

            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    raise sqlite3.IntegrityError(f"Tab name '{name}' already exists") from e
                raise

        return False  # Should not reach here, but satisfies type checker

    def update_tab(self, tab_id: int, name: Optional[str] = None, display_order: Optional[int] = None, color_hint: Optional[str] = None) -> bool:
        """Update an existing tab.
        
        Args:
            tab_id: ID of tab to update
            name: New name (optional)
            display_order: New display order (optional)
            color_hint: New color hint (optional)
            
        Returns: True if tab was updated, False if not found
        
        Raises:
            sqlite3.IntegrityError: If name already exists
            ValueError: If tab_id is invalid or no updates provided
        """
        if tab_id <= 0:
            raise ValueError("tab_id must be a positive integer")
            
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            
            try:
                updates: list[str] = []
                params: list[Any] = []
                
                if name is not None:
                    # Check if it's a system tab - don't allow renaming system tabs
                    cursor = conn.execute("SELECT tab_type FROM tabs WHERE id = ?", (tab_id,))
                    row = cursor.fetchone()
                    if not row:
                        return False
                    if row[0] == 'system':
                        raise ValueError("Cannot rename system tabs")
                    
                    updates.append("name = ?")
                    params.append(name)
                    
                if display_order is not None:
                    updates.append("display_order = ?")
                    params.append(display_order)
                    
                if color_hint is not None:
                    updates.append("color_hint = ?")
                    params.append(color_hint)
                
                if not updates:
                    raise ValueError("No updates provided")
                    
                updates.append("updated_ts = strftime('%s', 'now')")
                params.append(tab_id)
                
                # If renaming the tab, also update galleries assigned to this tab
                if name is not None:
                    # Get the current tab name before updating
                    cursor = conn.execute("SELECT name FROM tabs WHERE id = ?", (tab_id,))
                    row = cursor.fetchone()
                    if row:
                        old_name = row[0]

                        # Update the tab
                        sql = f"UPDATE tabs SET {', '.join(updates)} WHERE id = ?"
                        cursor = conn.execute(sql, params)

                        if cursor.rowcount > 0:
                            # Update all galleries assigned to this tab (both tab_name and tab_id if exists)
                            # Check if tab_id column exists first
                            cursor = conn.execute("PRAGMA table_info(galleries)")
                            columns = [column[1] for column in cursor.fetchall()]
                            has_tab_id = 'tab_id' in columns

                            if has_tab_id:
                                # Update tab_name for galleries with this tab_id
                                conn.execute(
                                    "UPDATE galleries SET tab_name = ? WHERE tab_id = ?",
                                    (name, tab_id)
                                )
                            else:
                                # Fallback to tab_name-based update
                                conn.execute(
                                    "UPDATE galleries SET tab_name = ? WHERE tab_name = ?",
                                    (name, old_name)
                                )
                            return True
                        return False
                    return False  # Tab not found
                else:
                    # No name change, just update other fields
                    sql = f"UPDATE tabs SET {', '.join(updates)} WHERE id = ?"
                    cursor = conn.execute(sql, params)
                    return cursor.rowcount > 0
                
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    raise sqlite3.IntegrityError(f"Tab name '{name}' already exists") from e
                raise

    def update_item_custom_field(self, path: str, field_name: str, value: str) -> bool:
        """Update a custom field for a gallery item.
        
        Args:
            path: Path to the gallery
            field_name: Name of the custom field (custom1, custom2, custom3, custom4)
            value: New value to set
            
        Returns:
            True if update was successful, False otherwise
        """
        # Allow both custom1-4 and ext1-4 fields (ext fields added in migration)
        valid_fields = ['custom1', 'custom2', 'custom3', 'custom4', 'ext1', 'ext2', 'ext3', 'ext4']
        if field_name not in valid_fields:
            log(f"Invalid custom field name: {field_name}, must be one of: {valid_fields}", level="warning", category="database")
            return False

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            try:
                cursor = conn.execute(f"UPDATE galleries SET {field_name} = ? WHERE path = ?", (value, path))
                rows_affected = cursor.rowcount

                # Verify the update by reading back the value
                verification_cursor = conn.execute(f"SELECT {field_name} FROM galleries WHERE path = ?", (path,))
                verification_cursor.fetchone()

                return rows_affected > 0
            except Exception as e:
                log(f"Error updating {field_name} for {path}: {e}", level="error", category="database")
                return False

    def update_item_template(self, path: str, template_name: str) -> bool:
        """Update the template name for a gallery item.
        
        Args:
            path: Path to the gallery
            template_name: New template name to set
            
        Returns:
            True if update was successful, False otherwise
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute(
                "UPDATE galleries SET template = ? WHERE path = ?",
                (template_name, path)
            )
            return cursor.rowcount > 0

    def update_item_image_host(self, path: str, image_host_id: str) -> bool:
        """Update the image host for a gallery item."""
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute(
                "UPDATE galleries SET image_host_id = ? WHERE path = ?",
                (image_host_id, path)
            )
            return cursor.rowcount > 0

    def delete_tab(self, tab_id: int, reassign_to: str = 'Main') -> Tuple[bool, int]:
        """Delete a tab and reassign its galleries to another tab.
        
        Args:
            tab_id: ID of tab to delete
            reassign_to: Tab name to reassign galleries to (default: 'Main')
            
        Returns: Tuple of (success, galleries_reassigned_count)
        
        Raises:
            ValueError: If trying to delete a system tab or invalid tab_id
        """
        if tab_id <= 0:
            raise ValueError("tab_id must be a positive integer")
            
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            try:
                # Get tab info before deletion
                cursor = conn.execute("SELECT name, tab_type FROM tabs WHERE id = ?", (tab_id,))
                row = cursor.fetchone()
                if not row:
                    return False, 0

                tab_name, tab_type = row[0], row[1]

                # Prevent deletion of system tabs
                if tab_type == 'system':
                    raise ValueError(f"Cannot delete system tab '{tab_name}'")
                
                # Verify destination tab exists
                cursor = conn.execute("SELECT COUNT(*) FROM tabs WHERE name = ? AND is_active = 1", (reassign_to,))
                if cursor.fetchone()[0] == 0:
                    raise ValueError(f"Destination tab '{reassign_to}' does not exist")

                # Get reassign_to tab_id
                cursor = conn.execute("SELECT id FROM tabs WHERE name = ? AND is_active = 1", (reassign_to,))
                reassign_row = cursor.fetchone()
                reassign_tab_id = reassign_row[0] if reassign_row else None

                # Reassign galleries to new tab using tab_id if available
                cursor = conn.execute("PRAGMA table_info(galleries)")
                columns = [column[1] for column in cursor.fetchall()]
                has_tab_id = 'tab_id' in columns

                if has_tab_id and reassign_tab_id:
                    # Use tab_id for reassignment
                    cursor = conn.execute(
                        "UPDATE galleries SET tab_id = ?, tab_name = ? WHERE tab_id = ?",
                        (reassign_tab_id, reassign_to, tab_id)
                    )
                else:
                    # Fallback to tab_name-based reassignment
                    cursor = conn.execute(
                        "UPDATE galleries SET tab_name = ? WHERE tab_name = ?",
                        (reassign_to, tab_name)
                    )
                galleries_moved = cursor.rowcount if hasattr(cursor, 'rowcount') else 0

                # Delete the tab
                cursor = conn.execute("DELETE FROM tabs WHERE id = ?", (tab_id,))
                tab_deleted = cursor.rowcount > 0 if hasattr(cursor, 'rowcount') else False

                if tab_deleted:
                    return True, galleries_moved
                else:
                    return False, 0

            except Exception as e:
                if isinstance(e, ValueError):
                    raise  # Re-raise ValueError with original message
                log(f"Error deleting tab {tab_id}: {e}", level="error", category="database")
                return False, 0

    def move_galleries_to_tab(self, gallery_paths: List[str], new_tab_name: str) -> int:
        """Move multiple galleries to a different tab.
        
        Args:
            gallery_paths: List of gallery paths to move
            new_tab_name: Name of destination tab
            
        Returns: Number of galleries moved
        
        Raises:
            ValueError: If new_tab_name is invalid or gallery_paths is empty
        """
        if not gallery_paths:
            return 0
            
        if not new_tab_name or not new_tab_name.strip():
            raise ValueError("new_tab_name cannot be empty")
        
        # Strip count from tab name (e.g., "Main (0)" -> "Main")
        import re
        clean_tab_name = re.sub(r'\s*\(\d+\)$', '', new_tab_name.strip())
            
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            
            try:
                # Get destination tab ID using clean tab name
                cursor = conn.execute("SELECT id FROM tabs WHERE name = ? AND is_active = 1", (clean_tab_name,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Destination tab '{clean_tab_name}' does not exist")
                
                tab_id = row[0]
                
                # Build parameterized query for bulk update using tab_id and clean name
                placeholders = ','.join(['?'] * len(gallery_paths))
                sql = f"UPDATE galleries SET tab_id = ?, tab_name = ? WHERE path IN ({placeholders})"
                params = [tab_id, clean_tab_name] + gallery_paths
                
                cursor = conn.execute(sql, params)
                moved_count = cursor.rowcount if hasattr(cursor, 'rowcount') else 0
                
                return moved_count
                
            except Exception as e:
                if isinstance(e, ValueError):
                    raise  # Re-raise ValueError with original message
                log(f"Error moving galleries to tab '{new_tab_name}': {e}", level="error", category="database")
                return 0

    def reorder_tabs(self, tab_orders: List[Tuple[int, int]]) -> None:
        """Reorder tabs by updating display_order for multiple tabs.
        
        Args:
            tab_orders: List of (tab_id, new_display_order) tuples
            
        Raises:
            ValueError: If tab_orders is invalid or contains invalid tab IDs
        """
        if not tab_orders:
            return
            
        # Validate input
        for tab_id, new_order in tab_orders:
            if not isinstance(tab_id, int) or tab_id <= 0:
                raise ValueError(f"Invalid tab_id: {tab_id}")
            if not isinstance(new_order, int) or new_order < 0:
                raise ValueError(f"Invalid display_order: {new_order}")
            
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            
            try:
                updated_count = 0
                for tab_id, new_order in tab_orders:
                    cursor = conn.execute(
                        "UPDATE tabs SET display_order = ?, updated_ts = strftime('%s', 'now') WHERE id = ?",
                        (new_order, tab_id)
                    )
                    if cursor.rowcount == 0:
                        log(f"Tab ID {tab_id} not found during reordering", level="warning", category="database")
                    else:
                        updated_count += 1


            except Exception as e:
                log(f"Error reordering tabs: {e}", level="error", category="database")
                raise

    def initialize_default_tabs(self) -> None:
        """Initialize default system tabs if they don't exist.

        This creates the default 'Main' system tab with proper ordering.
        Safe to call multiple times - will not create duplicates.
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            _initialize_default_tabs(conn)
    
    def ensure_migrations_complete(self) -> None:
        """Ensure all database migrations have been run.

        This method can be called explicitly if you need to ensure migrations
        are up to date without creating a new connection.
        """
        with _ConnectionContext(self.db_path) as conn:
            _run_migrations(conn)

    # ----------------------------- File Host Uploads ----------------------------

    def add_file_host_upload(
        self,
        gallery_path: str,
        host_name: str,
        status: str = 'pending',
        part_number: int = 0,
        blocked_by_upload_id: Optional[int] = None,
        dedup_only: int = 0,
        source_bytes: int = 0,
    ) -> Optional[int]:
        """Add a new file host upload record for a gallery.

        Args:
            gallery_path: Path to the gallery folder
            host_name: Name of the file host (e.g., 'rapidgator', 'gofile')
            status: Initial status ('pending', 'uploading', 'completed', 'failed',
                    'cancelled', 'blocked')
            part_number: Archive part number (0 for non-split, 1+ for split parts)
            blocked_by_upload_id: If this row is 'blocked', the upload_id of the
                primary row it waits on. None for non-blocked rows.
            dedup_only: 1 if this row should skip full upload and only attempt
                try_create_by_hash. Used for retry-after-sibling-success; terminal
                on failure (no fallback to full upload).

        Returns:
            Upload ID if created, None if failed
        """
        # Compute source size from the path if not provided by the caller.
        # This is the size of what will actually be uploaded (file or folder),
        # used for the queue bytes display before the upload starts.
        if source_bytes == 0:
            try:
                p = os.path.normpath(gallery_path)
                if os.path.isfile(p):
                    source_bytes = os.path.getsize(p)
                elif os.path.isdir(p):
                    source_bytes = sum(
                        os.path.getsize(os.path.join(p, f))
                        for f in os.listdir(p)
                        if os.path.isfile(os.path.join(p, f))
                    )
            except OSError:
                pass

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Normalize path to prevent duplicate records
            gallery_path = os.path.normpath(gallery_path)
            
            # Get Main tab ID and next insertion order
            cursor = conn.execute("SELECT id FROM tabs WHERE name = 'Main' AND is_active = 1")
            tab_row = cursor.fetchone()
            tab_id = tab_row[0] if tab_row else 1
            
            cursor = conn.execute("SELECT COALESCE(MAX(insertion_order), 0) + 1 FROM galleries")
            next_order = cursor.fetchone()[0]
            
            # Get gallery name with fallback for edge cases
            gallery_name = os.path.basename(gallery_path.rstrip('/\\')) or os.path.basename(os.path.dirname(gallery_path)) or 'Unknown Gallery'
            
            # Ensure gallery exists with correct status from CHECK constraint
            # Use ON CONFLICT DO NOTHING to avoid overwriting existing data
            conn.execute(
                """
                INSERT INTO galleries (path, name, status, tab_name, tab_id, added_ts, insertion_order)
                VALUES (?, ?, 'ready', 'Main', ?, strftime('%s', 'now'), ?)
                ON CONFLICT(path) DO NOTHING
                """,
                (gallery_path, gallery_name, tab_id, next_order)
            )
            
            # Get gallery ID (guaranteed to exist after INSERT)
            cursor = conn.execute("SELECT id FROM galleries WHERE path = ?", (gallery_path,))
            row = cursor.fetchone()
            if not row:
                # This should NEVER happen after INSERT
                log(f"Gallery SELECT failed after INSERT for path: {gallery_path}", level="critical", category="database")
                return None

            gallery_id = row[0]

            try:
                cursor = conn.execute(
                    """
                    INSERT OR REPLACE INTO file_host_uploads
                    (gallery_fk, host_name, status, part_number,
                     blocked_by_upload_id, dedup_only, total_bytes, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
                    """,
                    (gallery_id, host_name, status, part_number,
                     blocked_by_upload_id, dedup_only, source_bytes)
                )
                return cursor.lastrowid
            except Exception as e:
                log(f"Error adding file host upload: {e}", level="error", category="database")
                return None

    def get_file_host_uploads(self, gallery_path: str) -> List[Dict[str, Any]]:
        """Get all file host uploads for a gallery.

        Args:
            gallery_path: Path to the gallery folder

        Returns:
            List of upload records as dictionaries
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            cursor = conn.execute(
                """
                SELECT
                    fh.id, fh.gallery_fk, fh.host_name, fh.status,
                    fh.zip_path, fh.started_ts, fh.finished_ts,
                    fh.uploaded_bytes, fh.total_bytes,
                    fh.download_url, fh.file_id, fh.file_name, fh.error_message,
                    fh.raw_response, fh.retry_count, fh.created_ts,
                    COALESCE(fh.part_number, 0),
                    fh.md5_hash, fh.file_size, COALESCE(fh.deduped, 0),
                    fh.blocked_by_upload_id, COALESCE(fh.dedup_only, 0)
                FROM file_host_uploads fh
                JOIN galleries g ON fh.gallery_fk = g.id
                WHERE g.path = ?
                ORDER BY fh.host_name ASC, fh.part_number ASC
                """,
                (gallery_path,)
            )

            uploads = []
            for row in cursor.fetchall():
                uploads.append({
                    'id': row[0],
                    'gallery_fk': row[1],
                    'host_name': row[2],
                    'status': row[3],
                    'zip_path': row[4],
                    'started_ts': row[5],
                    'finished_ts': row[6],
                    'uploaded_bytes': row[7],
                    'total_bytes': row[8],
                    'download_url': row[9],
                    'file_id': row[10],
                    'file_name': row[11],
                    'error_message': row[12],
                    'raw_response': row[13],
                    'retry_count': row[14],
                    'created_ts': row[15],
                    'part_number': row[16],
                    'md5_hash': row[17],
                    'file_size': row[18],
                    'deduped': bool(row[19]),
                    'blocked_by_upload_id': row[20],
                    'dedup_only': bool(row[21]),
                })

            return uploads

    def get_all_file_host_uploads_batch(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all file host uploads in a single batch query (performance optimization).

        This method replaces 989 individual database queries with ONE query during startup,
        reducing database query time from 40-70 seconds to <1 second.

        Returns:
            Dictionary mapping gallery path to list of upload dictionaries.
            Each upload dictionary contains: id, gallery_fk, host_name, status,
            zip_path, started_ts, finished_ts, uploaded_bytes, total_bytes,
            download_url, file_id, file_name, error_message, raw_response,
            retry_count, created_ts
        """
        uploads_by_path: Dict[str, List[Dict[str, Any]]] = {}

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Single optimized query with JOIN - fetches ALL uploads for ALL galleries
            cursor = conn.execute(
                """
                SELECT
                    g.path,
                    fh.id, fh.gallery_fk, fh.host_name, fh.status,
                    fh.zip_path, fh.started_ts, fh.finished_ts,
                    fh.uploaded_bytes, fh.total_bytes,
                    fh.download_url, fh.file_id, fh.file_name, fh.error_message,
                    fh.raw_response, fh.retry_count, fh.created_ts,
                    COALESCE(fh.part_number, 0),
                    fh.md5_hash, fh.file_size, COALESCE(fh.deduped, 0)
                FROM file_host_uploads fh
                JOIN galleries g ON fh.gallery_fk = g.id
                ORDER BY g.path, fh.host_name ASC, fh.part_number ASC
                """
            )

            for row in cursor.fetchall():
                path = row[0]
                upload = {
                    'id': row[1],
                    'gallery_fk': row[2],
                    'host_name': row[3],
                    'status': row[4],
                    'zip_path': row[5],
                    'started_ts': row[6],
                    'finished_ts': row[7],
                    'uploaded_bytes': row[8],
                    'total_bytes': row[9],
                    'download_url': row[10],
                    'file_id': row[11],
                    'file_name': row[12],
                    'error_message': row[13],
                    'raw_response': row[14],
                    'retry_count': row[15],
                    'created_ts': row[16],
                    'part_number': row[17],
                    'md5_hash': row[18],
                    'file_size': row[19],
                    'deduped': bool(row[20]),
                }

                if path not in uploads_by_path:
                    uploads_by_path[path] = []
                uploads_by_path[path].append(upload)

        return uploads_by_path

    def update_file_host_upload(
        self,
        upload_id: int,
        **kwargs
    ) -> bool:
        """Update a file host upload record.

        Args:
            upload_id: ID of the upload record
            **kwargs: Fields to update (status, uploaded_bytes, total_bytes, download_url, etc.)

        Returns:
            True if updated successfully, False otherwise
        """
        if not kwargs:
            return False

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Build UPDATE query dynamically
            allowed_fields = {
                'status', 'zip_path', 'started_ts', 'finished_ts',
                'uploaded_bytes', 'total_bytes', 'download_url',
                'file_id', 'file_name', 'error_message', 'raw_response', 'retry_count',
                'md5_hash', 'file_size', 'deduped',
                'blocked_by_upload_id', 'dedup_only',
            }

            updates = []
            values = []
            for key, value in kwargs.items():
                if key in allowed_fields:
                    updates.append(f"{key} = ?")
                    values.append(value)

            if not updates:
                return False

            values.append(upload_id)

            try:
                cursor = conn.execute(
                    f"UPDATE file_host_uploads SET {', '.join(updates)} WHERE id = ?",
                    values
                )
                return cursor.rowcount > 0
            except Exception as e:
                log(f"Error updating file host upload: {e}", level="error", category="database")
                return False

    def delete_file_host_upload(self, upload_id: int) -> bool:
        """Delete a file host upload record.

        Args:
            upload_id: ID of the upload record

        Returns:
            True if deleted, False otherwise
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            try:
                cursor = conn.execute(
                    "DELETE FROM file_host_uploads WHERE id = ?",
                    (upload_id,)
                )
                return cursor.rowcount > 0
            except Exception as e:
                log(f"Error deleting file host upload: {e}", level="error", category="database")
                return False

    def get_pending_file_host_uploads(self, host_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pending file host uploads, optionally filtered by host.

        Args:
            host_name: Optional host name to filter by

        Returns:
            List of pending upload records with gallery information
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            if host_name:
                cursor = conn.execute(
                    """
                    SELECT
                        fh.id, fh.gallery_fk, fh.host_name, fh.status,
                        fh.retry_count, fh.created_ts,
                        g.path, g.name, g.status as gallery_status,
                        COALESCE(fh.part_number, 0),
                        COALESCE(fh.dedup_only, 0),
                        fh.blocked_by_upload_id,
                        fh.md5_hash,
                        fh.zip_path
                    FROM file_host_uploads fh
                    JOIN galleries g ON fh.gallery_fk = g.id
                    WHERE fh.status = 'pending' AND fh.host_name = ?
                    ORDER BY fh.created_ts ASC, fh.part_number ASC
                    """,
                    (host_name,)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT
                        fh.id, fh.gallery_fk, fh.host_name, fh.status,
                        fh.retry_count, fh.created_ts,
                        g.path, g.name, g.status as gallery_status,
                        COALESCE(fh.part_number, 0),
                        COALESCE(fh.dedup_only, 0),
                        fh.blocked_by_upload_id,
                        fh.md5_hash,
                        fh.zip_path
                    FROM file_host_uploads fh
                    JOIN galleries g ON fh.gallery_fk = g.id
                    WHERE fh.status = 'pending'
                    ORDER BY fh.created_ts ASC, fh.part_number ASC
                    """
                )

            uploads = []
            for row in cursor.fetchall():
                uploads.append({
                    'id': row[0],
                    'gallery_fk': row[1],
                    'host_name': row[2],
                    'status': row[3],
                    'retry_count': row[4],
                    'created_ts': row[5],
                    'gallery_path': row[6],
                    'gallery_name': row[7],
                    'gallery_status': row[8],
                    'part_number': row[9],
                    'dedup_only': row[10],
                    'blocked_by_upload_id': row[11],
                    'md5_hash': row[12],
                    'zip_path': row[13],
                })

            return uploads

    def get_family_completed_parts(
        self,
        gallery_fk: int,
        family: str,
    ) -> List[Dict[str, Any]]:
        """Return completed sibling part rows for a family, one per part_number.

        For use by the K2S family dedup path: reads sibling md5s from the DB so a
        secondary host can call try_create_by_hash without recomputing the hash
        from an archive. Only rows with a populated md5_hash are returned — legacy
        rows from before the hash-dedupe feature are excluded.

        When multiple family members have completed rows for the same part_number,
        the highest-priority host wins (per HOST_FAMILY_PRIORITY). This is a
        deterministic tiebreaker and matches primary selection order.

        Args:
            gallery_fk: Foreign key into galleries table.
            family: Family name (e.g., "k2s").

        Returns:
            List of dicts ordered by part_number. Each dict has:
            id, gallery_fk, host_name, part_number, md5_hash, file_name.
            Empty list if the family is unknown or no completed sibling exists.
        """
        members = HOST_FAMILY_PRIORITY.get(family)
        if not members:
            return []

        placeholders = ",".join("?" for _ in members)
        sql = f"""
            SELECT id, gallery_fk, host_name, part_number, md5_hash, file_name
            FROM file_host_uploads
            WHERE gallery_fk = ?
              AND host_name IN ({placeholders})
              AND status = 'completed'
              AND md5_hash IS NOT NULL
              AND md5_hash != ''
            ORDER BY part_number ASC
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            rows = conn.execute(sql, (gallery_fk, *members)).fetchall()

        # Collapse duplicates: prefer the highest-priority host for each part_number.
        priority_index = {host: idx for idx, host in enumerate(members)}
        by_part: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            entry = {
                "id": row[0],
                "gallery_fk": row[1],
                "host_name": row[2],
                "part_number": row[3],
                "md5_hash": row[4],
                "file_name": row[5],
            }
            existing = by_part.get(entry["part_number"])
            if existing is None:
                by_part[entry["part_number"]] = entry
                continue
            if priority_index[entry["host_name"]] < priority_index[existing["host_name"]]:
                by_part[entry["part_number"]] = entry

        return [by_part[k] for k in sorted(by_part)]

    def get_family_head_rows(
        self,
        gallery_fk: int,
        members: list,
    ) -> List[Dict[str, Any]]:
        """Return the head (part_number=0) rows for each given host_id for a gallery."""
        if not members:
            return []
        placeholders = ",".join("?" for _ in members)
        sql = f"""
            SELECT id, gallery_fk, host_name, status, part_number, blocked_by_upload_id, dedup_only, md5_hash
            FROM file_host_uploads
            WHERE gallery_fk = ?
              AND host_name IN ({placeholders})
              AND part_number = 0
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            rows = conn.execute(sql, (gallery_fk, *members)).fetchall()
        return [
            {
                "id": r[0],
                "gallery_fk": r[1],
                "host_name": r[2],
                "status": r[3],
                "part_number": r[4],
                "blocked_by_upload_id": r[5],
                "dedup_only": r[6],
                "md5_hash": r[7],
            }
            for r in rows
        ]

    def get_file_host_pending_stats(self, host_name: str) -> dict:
        """Get queue statistics for a specific file host.

        Efficient aggregated query for event-driven queue display updates.

        Args:
            host_name: Name of the file host

        Returns:
            Dict with 'files' (count) and 'bytes' (remaining bytes)
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute(
                """
                SELECT COUNT(*) as files,
                       COALESCE(SUM(total_bytes - uploaded_bytes), 0) as bytes
                FROM file_host_uploads
                WHERE host_name = ? AND status IN ('pending', 'uploading', 'blocked')
                """,
                (host_name,)
            )
            row = cursor.fetchone()
            return {'files': row[0], 'bytes': row[1]} if row else {'files': 0, 'bytes': 0}

    # ----------------------------- IMX Status Tracking ----------------------------

    def get_image_urls_for_galleries(self, gallery_paths: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """Get image URLs for multiple galleries in a single batch query.

        Optimized for checking gallery status on imx.to by fetching all image
        URLs for the specified galleries in one database query.

        Args:
            gallery_paths: List of gallery paths to retrieve image URLs for

        Returns:
            Dictionary mapping gallery_path to list of image dictionaries.
            Each image dictionary contains:
            - 'filename': The image filename
            - 'url': The imx.to image URL (e.g., 'https://imx.to/i/xxxxx')

        Example:
            {
                '/path/to/gallery1': [
                    {'filename': 'image1.jpg', 'url': 'https://imx.to/i/abc123'},
                    {'filename': 'image2.jpg', 'url': 'https://imx.to/i/def456'},
                ],
                '/path/to/gallery2': [...]
            }
        """
        if not gallery_paths:
            return {}

        result: Dict[str, List[Dict[str, str]]] = {}

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Build parameterized query for batch lookup
            placeholders = ','.join(['?'] * len(gallery_paths))
            cursor = conn.execute(
                f"""
                SELECT g.path, i.filename, i.url
                FROM images i
                JOIN galleries g ON i.gallery_fk = g.id
                WHERE g.path IN ({placeholders})
                  AND i.url IS NOT NULL
                  AND i.url != ''
                ORDER BY g.path, i.filename
                """,
                tuple(gallery_paths)
            )

            for row in cursor.fetchall():
                path, filename, url = row[0], row[1], row[2]
                if path not in result:
                    result[path] = []
                result[path].append({
                    'filename': filename,
                    'url': url
                })

        return result

    def update_gallery_imx_status(self, gallery_path: str, status_text: str, checked_timestamp: int) -> bool:
        """Update the IMX status for a gallery.

        Updates the imx_status and imx_status_checked columns for a gallery,
        used for tracking whether images are still online on imx.to.

        Args:
            gallery_path: Path to the gallery to update
            status_text: Status text (e.g., 'Online (342/342)', 'Partial (242/342)', 'Offline (0/342)')
            checked_timestamp: Unix timestamp of when the check was performed

        Returns:
            True if the gallery was updated, False if not found or update failed
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            try:
                cursor = conn.execute(
                    """
                    UPDATE galleries
                    SET imx_status = ?, imx_status_checked = ?
                    WHERE path = ?
                    """,
                    (status_text, checked_timestamp, gallery_path)
                )
                return cursor.rowcount > 0
            except Exception as e:
                log(f"Error updating IMX status for {gallery_path}: {e}", level="error", category="database")
                return False

    def bulk_update_gallery_imx_status(self, updates: List[Tuple[str, str, int]]) -> None:
        """Bulk update IMX online status for multiple galleries.

        Much more efficient than individual updates for large numbers of galleries.

        Args:
            updates: List of tuples (path, status_text, check_timestamp)
                     - path: Gallery path
                     - status_text: Status like "Online (10/10)" or "Partial (5/10)"
                     - check_timestamp: Unix timestamp of check
        """
        if not updates:
            return

        try:
            with _ConnectionContext(self.db_path) as conn:
                _ensure_schema(conn)
                # Reorder tuple: input is (path, status, timestamp) but SQL needs (status, timestamp, path)
                # to match the SET clause order followed by WHERE clause
                conn.executemany(
                    "UPDATE galleries SET imx_status = ?, imx_status_checked = ? WHERE path = ?",
                    [(status, timestamp, path) for path, status, timestamp in updates]
                )
            log(f"Bulk updated IMX status for {len(updates)} galleries",
                level="debug", category="database")
        except Exception as e:
            log(f"Failed to bulk update IMX status: {e}", level="error", category="database")
            raise

    def bulk_upsert_scan_results(
        self, results: List[Tuple[int, str, str, str, int, int, int, Optional[str]]]
    ) -> None:
        """Bulk upsert scan results for the multi-host link scanner.

        Each tuple: (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts, detail_json)

        Uses INSERT OR REPLACE on the UNIQUE(gallery_fk, host_type, host_id) constraint.
        """
        if not results:
            return
        try:
            with _ConnectionContext(self.db_path) as conn:
                _ensure_schema(conn)
                conn.executemany(
                    """INSERT OR REPLACE INTO host_scan_results
                       (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts, detail_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    results
                )
            log(f"Upserted {len(results)} scan results", level="debug", category="database")
        except Exception as e:
            log(f"Failed to upsert scan results: {e}", level="error", category="database")
            raise

    def get_hosts_with_uploads(self) -> Dict[Tuple[str, str], Dict[str, int]]:
        """Get all hosts that have completed uploads, with gallery and image counts.

        Queries galleries (for image hosts) and file_host_uploads (for file hosts)
        to discover which hosts actually have uploads in the database.

        Returns:
            Dict keyed by (host_type, host_id) tuples, values are
            {'gallery_count': int, 'image_count': int}.
        """
        result: Dict[Tuple[str, str], Dict[str, int]] = {}

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Image hosts from galleries table
            cursor = conn.execute("""
                SELECT image_host_id, COUNT(*) as gal_cnt,
                       COALESCE(SUM(total_images), 0) as img_cnt
                FROM galleries
                WHERE status = 'completed' AND image_host_id IS NOT NULL
                GROUP BY image_host_id
            """)
            for row in cursor.fetchall():
                result[('image', row[0])] = {
                    'gallery_count': row[1],
                    'image_count': row[2],
                }

            # File hosts from file_host_uploads table
            cursor = conn.execute("""
                SELECT host_name, COUNT(DISTINCT gallery_fk) as gal_cnt,
                       COUNT(*) as file_cnt
                FROM file_host_uploads
                WHERE status = 'completed'
                GROUP BY host_name
            """)
            for row in cursor.fetchall():
                result[('file', row[0])] = {
                    'gallery_count': row[1],
                    'image_count': row[2],
                }

        return result

    def get_scan_stats_by_host(self) -> Dict[Tuple[str, str], Dict[str, int]]:
        """Get aggregated scan statistics grouped by (host_type, host_id).

        Returns:
            Dict keyed by (host_type, host_id) tuples, each value containing:
            - online_galleries, partial_galleries, offline_galleries, error_galleries
            - total_online (sum of online_count), total_items (sum of total_count)
        """
        result: Dict[Tuple[str, str], Dict[str, int]] = {}

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute("""
                SELECT host_type, host_id, status,
                       COUNT(*) as gallery_count,
                       SUM(online_count) as sum_online,
                       SUM(total_count) as sum_total
                FROM host_scan_results
                GROUP BY host_type, host_id, status
            """)

            for row in cursor.fetchall():
                host_type, host_id, status = row[0], row[1], row[2]
                gallery_count, sum_online, sum_total = row[3], row[4] or 0, row[5] or 0
                key = (host_type, host_id)

                if key not in result:
                    result[key] = {
                        'online_galleries': 0, 'partial_galleries': 0,
                        'offline_galleries': 0, 'error_galleries': 0,
                        'total_online': 0, 'total_items': 0,
                    }

                result[key][f'{status}_galleries'] = gallery_count
                result[key]['total_online'] += sum_online
                result[key]['total_items'] += sum_total

        return result

    def get_scan_status_by_gallery_host(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Get per-gallery per-host scan status for the main queue table overlay.

        Returns:
            Dict keyed by (gallery_path, host_id) with values:
            {status: str, online_count: int, total_count: int, checked_ts: int}
        """
        result: Dict[Tuple[str, str], Dict[str, Any]] = {}
        try:
            with _ConnectionContext(self.db_path) as conn:
                _ensure_schema(conn)
                cursor = conn.execute("""
                    SELECT g.path, hsr.host_id, hsr.status,
                           hsr.online_count, hsr.total_count, hsr.checked_ts
                    FROM host_scan_results hsr
                    JOIN galleries g ON g.id = hsr.gallery_fk
                """)
                for row in cursor.fetchall():
                    key = (row[0], row[1])
                    result[key] = {
                        'status': row[2],
                        'online_count': row[3],
                        'total_count': row[4],
                        'checked_ts': row[5],
                    }
        except Exception as e:
            log(f"Failed to load scan status cache: {e}", level="warning", category="database")
        return result

    def get_worst_status_for_gallery(self, gallery_fk: int) -> Optional[Dict[str, Any]]:
        """Get the worst scan status across all hosts for a gallery.

        Status priority (worst first): offline > partial > online.

        Returns:
            Dict with worst_status, total_online, total_items, hosts list.
            None if no scan results exist.
        """
        try:
            with _ConnectionContext(self.db_path) as conn:
                _ensure_schema(conn)
                rows = conn.execute(
                    "SELECT host_type, host_id, status, online_count, total_count, checked_ts "
                    "FROM host_scan_results WHERE gallery_fk = ?",
                    (gallery_fk,)
                ).fetchall()

            if not rows:
                return None

            hosts = []
            total_online = 0
            total_items = 0
            has_offline = False
            has_partial = False

            for host_type, host_id, status, online, total, checked_ts in rows:
                hosts.append({
                    'host_type': host_type,
                    'host_id': host_id,
                    'status': status,
                    'online': online,
                    'total': total,
                    'checked_ts': checked_ts,
                })
                total_online += online
                total_items += total
                if status == 'offline':
                    has_offline = True
                elif status == 'partial':
                    has_partial = True

            if has_offline:
                worst = 'offline'
            elif has_partial:
                worst = 'partial'
            else:
                worst = 'online'

            return {
                'worst_status': worst,
                'total_online': total_online,
                'total_items': total_items,
                'hosts': hosts,
            }
        except Exception as e:
            log(f"Error getting worst status for gallery {gallery_fk}: {e}",
                level="error", category="database")
            return None

    def get_galleries_for_dashboard(self) -> List[Dict[str, Any]]:
        """Get all completed galleries per host for dashboard tab display.

        Returns every gallery with its upload host, LEFT JOINing scan results
        so unchecked galleries still appear. Image host galleries come from
        galleries.image_host_id; file host galleries from file_host_uploads.

        Returns:
            List of dicts with keys: host_id, host_type, gallery_name,
            total_images, online, total, checked_ts.
        """
        results = []
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Image host galleries
            rows = conn.execute("""
                SELECT g.image_host_id, g.name, g.total_images,
                       hsr.online_count, hsr.total_count,
                       strftime('%Y-%m-%d %H:%M', hsr.checked_ts, 'unixepoch', 'localtime'),
                       strftime('%Y-%m-%d %H:%M', g.finished_ts, 'unixepoch', 'localtime')
                FROM galleries g
                LEFT JOIN host_scan_results hsr
                    ON hsr.gallery_fk = g.id
                    AND hsr.host_type = 'image'
                    AND hsr.host_id = g.image_host_id
                WHERE g.status = 'completed'
                    AND g.image_host_id IS NOT NULL
                ORDER BY g.image_host_id, g.name
            """).fetchall()
            for row in rows:
                results.append({
                    'host_id': row[0],
                    'host_type': 'image',
                    'gallery_name': row[1] or '(unnamed)',
                    'total_images': row[2] or 0,
                    'online': row[3],       # None if no scan
                    'total': row[4],        # None if no scan
                    'checked_ts': row[5] or '',
                    'upload_ts': row[6] or '',
                })

            # File host galleries (grouped — one row per gallery per host)
            rows = conn.execute("""
                SELECT fhu.host_name, g.name,
                       hsr.online_count, hsr.total_count,
                       strftime('%Y-%m-%d %H:%M', hsr.checked_ts, 'unixepoch', 'localtime'),
                       strftime('%Y-%m-%d %H:%M', MAX(fhu.finished_ts), 'unixepoch', 'localtime')
                FROM file_host_uploads fhu
                JOIN galleries g ON g.id = fhu.gallery_fk
                LEFT JOIN host_scan_results hsr
                    ON hsr.gallery_fk = fhu.gallery_fk
                    AND hsr.host_type = 'file'
                    AND hsr.host_id = fhu.host_name
                WHERE fhu.status = 'completed'
                GROUP BY fhu.gallery_fk, fhu.host_name
                ORDER BY fhu.host_name, g.name
            """).fetchall()
            for row in rows:
                results.append({
                    'host_id': row[0],
                    'host_type': 'file',
                    'gallery_name': row[1] or '(unnamed)',
                    'total_images': 1,      # file hosts have 1 file per upload
                    'online': row[2],       # None if no scan
                    'total': row[3],        # None if no scan
                    'checked_ts': row[4] or '',
                    'upload_ts': row[5] or '',
                })

        return results

    def get_galleries_for_scan(
        self, age_days: int, host_filter: str, scan_type: str,
        age_mode: str = 'last_scan'
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get galleries and file uploads eligible for scanning.

        Args:
            age_days: Minimum days since last check (for 'age' scan_type).
                      0 means 'All' — skip age filtering entirely.
            host_filter: Host ID to filter, or '' for all hosts.
            scan_type: 'age' (not checked in X days), 'unchecked' (never checked),
                       or 'problems' (offline/partial only).
            age_mode: For 'age' scan_type — 'last_scan' filters by checked_ts,
                      'upload' filters by gallery finished_ts.

        Returns:
            Dict with 'image_galleries' and 'file_uploads' lists, shaped for
            ScanCoordinator.start_scan().
        """
        result: Dict[str, List[Dict[str, Any]]] = {
            'image_galleries': [],
            'file_uploads': [],
        }
        now = int(time.time())
        cutoff_ts = now - (age_days * 86400)

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # --- Image host galleries ---
            image_query = """
                SELECT g.id, g.image_host_id, g.name
                FROM galleries g
                LEFT JOIN host_scan_results hsr
                    ON hsr.gallery_fk = g.id
                    AND hsr.host_type = 'image'
                    AND hsr.host_id = g.image_host_id
                WHERE g.status = 'completed'
                    AND g.image_host_id IS NOT NULL
            """
            params: list = []

            if host_filter:
                image_query += " AND g.image_host_id = ?"
                params.append(host_filter)

            if scan_type == 'age':
                if age_days == 0:
                    pass  # No age filter — return all
                elif age_mode == 'upload':
                    image_query += " AND (g.finished_ts IS NULL OR g.finished_ts < ?)"
                    params.append(cutoff_ts)
                else:  # 'last_scan' (default)
                    image_query += " AND (hsr.checked_ts IS NULL OR hsr.checked_ts < ?)"
                    params.append(cutoff_ts)
            elif scan_type == 'unchecked':
                image_query += " AND hsr.checked_ts IS NULL"
            elif scan_type == 'problems':
                image_query += " AND hsr.status IN ('offline', 'partial')"

            for row in conn.execute(image_query, params).fetchall():
                gal_id, host_id, name = row[0], row[1], row[2]

                # Gather URLs for this gallery
                url_rows = conn.execute(
                    "SELECT url, thumb_url FROM images WHERE gallery_fk = ? AND (url IS NOT NULL OR thumb_url IS NOT NULL)",
                    (gal_id,)
                ).fetchall()
                image_urls = [r[0] for r in url_rows if r[0]]
                thumb_urls = [r[1] for r in url_rows if r[1]]

                result['image_galleries'].append({
                    'db_id': gal_id,
                    'image_host_id': host_id,
                    'name': name,
                    'thumb_urls': thumb_urls,
                    'image_urls': image_urls,
                })

            # --- File host uploads ---
            file_query = """
                SELECT fhu.gallery_fk, fhu.host_name, fhu.file_id, fhu.download_url
                FROM file_host_uploads fhu
                LEFT JOIN host_scan_results hsr
                    ON hsr.gallery_fk = fhu.gallery_fk
                    AND hsr.host_type = 'file'
                    AND hsr.host_id = fhu.host_name
                WHERE fhu.status = 'completed'
            """
            fparams: list = []

            if host_filter:
                file_query += " AND fhu.host_name = ?"
                fparams.append(host_filter)

            if scan_type == 'age':
                if age_days == 0:
                    pass  # No age filter — return all
                elif age_mode == 'upload':
                    file_query += " AND EXISTS (SELECT 1 FROM galleries g2 WHERE g2.id = fhu.gallery_fk AND (g2.finished_ts IS NULL OR g2.finished_ts < ?))"
                    fparams.append(cutoff_ts)
                else:  # 'last_scan' (default)
                    file_query += " AND (hsr.checked_ts IS NULL OR hsr.checked_ts < ?)"
                    fparams.append(cutoff_ts)
            elif scan_type == 'unchecked':
                file_query += " AND hsr.checked_ts IS NULL"
            elif scan_type == 'problems':
                file_query += " AND hsr.status IN ('offline', 'partial')"

            for row in conn.execute(file_query, fparams).fetchall():
                result['file_uploads'].append({
                    'gallery_fk': row[0],
                    'host_name': row[1],
                    'file_id': row[2] or '',
                    'download_url': row[3] or '',
                })

        return result

    def get_galleries_by_check_age(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get completed galleries grouped by how long ago they were checked.

        Groups galleries into time buckets based on imx_status_checked timestamp:
        - never: Never checked (NULL or 0)
        - 0-7: Checked within last 7 days
        - 8-14: Checked 8-14 days ago
        - 15-30: Checked 15-30 days ago
        - 31-60: Checked 31-60 days ago
        - 61-90: Checked 61-90 days ago
        - 91-365: Checked 91-365 days ago
        - 365+: Checked more than 365 days ago

        Returns:
            Dict with bucket names as keys and lists of gallery dicts as values.
            Each gallery dict contains: path, name, db_id, imx_status, imx_status_checked
        """
        buckets: Dict[str, List[Dict[str, Any]]] = {
            'never': [],
            '0-7': [],
            '8-14': [],
            '15-30': [],
            '31-60': [],
            '61-90': [],
            '91-365': [],
            '365+': []
        }

        now = int(time.time())
        day_seconds = 86400

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            cursor = conn.execute("""
                SELECT id, path, name, imx_status, imx_status_checked
                FROM galleries
                WHERE status = 'completed'
                ORDER BY imx_status_checked ASC NULLS FIRST
            """)

            for row in cursor.fetchall():
                gallery = {
                    'db_id': row[0],
                    'path': row[1],
                    'name': row[2] or os.path.basename(row[1]),
                    'imx_status': row[3] or '',
                    'imx_status_checked': row[4]
                }

                checked_ts = row[4]
                if not checked_ts:
                    buckets['never'].append(gallery)
                else:
                    age_days = (now - checked_ts) // day_seconds
                    if age_days <= 7:
                        buckets['0-7'].append(gallery)
                    elif age_days <= 14:
                        buckets['8-14'].append(gallery)
                    elif age_days <= 30:
                        buckets['15-30'].append(gallery)
                    elif age_days <= 60:
                        buckets['31-60'].append(gallery)
                    elif age_days <= 90:
                        buckets['61-90'].append(gallery)
                    elif age_days <= 365:
                        buckets['91-365'].append(gallery)
                    else:
                        buckets['365+'].append(gallery)

        return buckets

    def get_link_scanner_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics for the Link Scanner dashboard.

        Returns gallery and image status counts, plus cumulative counts for
        galleries by check age (how long since they were scanned).

        Returns:
            Dict containing:
            - galleries: {online, offline, partial, never, total}
            - images: {online, offline, unknown, total}
            - cumulative_counts: {7: count_7plus, 14: count_14plus, ...}
            - galleries_by_age: {7: [galleries], 14: [galleries], ...}
            - offline_partial_galleries: [galleries with offline/partial status]
            - never_checked_galleries: [galleries never scanned]
        """
        stats: Dict[str, Any] = {
            'galleries': {'online': 0, 'offline': 0, 'partial': 0, 'never': 0, 'total': 0},
            'images': {'online': 0, 'offline': 0, 'unknown': 0, 'total': 0},
            'cumulative_counts': {},
            'galleries_by_age': {},
            'offline_partial_galleries': [],
            'never_checked_galleries': []
        }

        now = int(time.time())
        day_seconds = 86400

        # Age thresholds for cumulative counts (in days)
        age_thresholds = [7, 14, 30, 60, 90, 365, 0]  # 0 = all

        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)

            # Get all completed galleries with their status info
            cursor = conn.execute("""
                SELECT id, path, name, imx_status, imx_status_checked
                FROM galleries
                WHERE status = 'completed'
                ORDER BY imx_status_checked ASC NULLS FIRST
            """)

            all_galleries = []
            for row in cursor.fetchall():
                gallery = {
                    'db_id': row[0],
                    'path': row[1],
                    'name': row[2] or os.path.basename(row[1]),
                    'imx_status': row[3] or '',
                    'imx_status_checked': row[4]
                }
                all_galleries.append(gallery)

                # Count by status
                status = gallery['imx_status'].lower()
                if not gallery['imx_status_checked']:
                    stats['galleries']['never'] += 1
                    stats['never_checked_galleries'].append(gallery)
                elif 'offline' in status:
                    stats['galleries']['offline'] += 1
                    stats['offline_partial_galleries'].append(gallery)
                elif 'partial' in status:
                    stats['galleries']['partial'] += 1
                    stats['offline_partial_galleries'].append(gallery)
                elif status and ('online' in status or 'ok' in status):
                    stats['galleries']['online'] += 1

            stats['galleries']['total'] = len(all_galleries)

            # Build cumulative counts by age
            for threshold in age_thresholds:
                galleries_in_range = []

                for gallery in all_galleries:
                    checked_ts = gallery['imx_status_checked']

                    if threshold == 0:
                        # All galleries
                        galleries_in_range.append(gallery)
                    elif not checked_ts:
                        # Never checked - always include in cumulative
                        galleries_in_range.append(gallery)
                    else:
                        age_days = (now - checked_ts) // day_seconds
                        if age_days >= threshold:
                            galleries_in_range.append(gallery)

                stats['cumulative_counts'][threshold] = len(galleries_in_range)
                stats['galleries_by_age'][threshold] = galleries_in_range

            # Get image count from completed galleries
            # Note: Image-level status isn't tracked - only gallery-level imx_status
            # So we just count total images from completed galleries
            cursor = conn.execute("""
                SELECT COUNT(*) as total
                FROM images i
                INNER JOIN galleries g ON i.gallery_fk = g.id
                WHERE g.status = 'completed'
            """)

            row = cursor.fetchone()
            if row:
                stats['images']['total'] = row[0] or 0
                # Image-level online/offline not tracked - derive from gallery status
                stats['images']['online'] = 0
                stats['images']['offline'] = 0
                stats['images']['unknown'] = stats['images']['total']

        return stats

    def update_gallery_path(self, old_path: str, new_path: str) -> bool:
        """Update a gallery's path when it has been relocated.

        Args:
            old_path: Original gallery path
            new_path: New gallery path

        Returns:
            True if update was successful, False otherwise
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            try:
                old_path = os.path.normpath(old_path)
                new_path = os.path.normpath(new_path)

                cursor = conn.execute(
                    "UPDATE galleries SET path = ? WHERE path = ?",
                    (new_path, old_path)
                )

                if cursor.rowcount > 0:
                    log(f"Relocated gallery: {old_path} -> {new_path}",
                        level="info", category="database")
                    return True
                return False
            except Exception as e:
                log(f"Error updating gallery path: {e}", level="error", category="database")
                return False

    def get_galleries_by_parent_folder(self, parent_folder: str) -> List[Dict[str, Any]]:
        """Get all galleries that are children of a parent folder.

        Args:
            parent_folder: Parent directory path

        Returns:
            List of gallery records whose paths are under parent_folder
        """
        with _ConnectionContext(self.db_path) as conn:
            _ensure_schema(conn)
            parent_prefix = os.path.normpath(parent_folder).rstrip(os.sep) + os.sep
            # Escape LIKE special characters to prevent unintended matches
            escaped_prefix = parent_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            cursor = conn.execute(
                "SELECT id, path, name, status FROM galleries WHERE path LIKE ? ESCAPE '\\'",
                (escaped_prefix + "%",)
            )
            return [
                {'id': r[0], 'path': r[1], 'name': r[2], 'status': r[3]}
                for r in cursor.fetchall()
            ]

