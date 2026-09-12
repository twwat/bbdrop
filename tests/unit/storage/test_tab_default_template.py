"""Per-tab default BBCode template: migration 20 + resolution in add_item.

A tab may carry a `default_template`. When set, it OVERRIDES whatever
template_name the caller passed to add_item -- it is not a default *for*
that argument. That is what "the tab default wins with no exceptions"
means, and it is what makes the video path correct: the tab default beats
Video -> default_template too (gallery_queue_controller.py:265), while a
NULL tab default leaves that chain byte-for-byte untouched.

NULL (and '') mean "None (Current selection)" -- fall through to the
caller's value.

Storage is a column on `tabs`, read by name. Rename is an in-place
UPDATE ... WHERE id = ? (database.py:1771), so the row id never changes
and the setting survives -- pinned by the rename test below.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from src.storage.database import (
    QueueStore,
    _ensure_schema,
    _schema_initialized_dbs,
)


@pytest.fixture
def conn():
    """Real-file sqlite DB so the schema-cache early-return doesn't bite us."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    _ensure_schema(db)
    yield db
    db.close()
    _schema_initialized_dbs.discard(path)
    try:
        os.unlink(path)
    except OSError:
        pass


def _set_default(store, tab_name, template):
    """Write tabs.default_template directly.

    The production writer is the Tab Settings panel, which uses its own
    connection (matching its forum-posting siblings); QueueStore deliberately
    exposes no setter, so tests write the column the same way several sibling
    storage tests already do.
    """
    with sqlite3.connect(store.db_path) as c:
        c.execute(
            "UPDATE tabs SET default_template = ? WHERE name = ?",
            (template, tab_name),
        )


@pytest.fixture
def store():
    """A QueueStore on a throwaway db file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # QueueStore creates it
    s = QueueStore(db_path=path)
    yield s
    _schema_initialized_dbs.discard(path)
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Migration 20
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMigration20:

    def test_tabs_has_default_template_column(self, conn):
        columns = {c[1] for c in conn.execute("PRAGMA table_info(tabs)").fetchall()}
        assert "default_template" in columns

    def test_existing_tabs_default_to_null(self, conn):
        """ADD COLUMN with no DEFAULT gives every existing row NULL, which is
        exactly the "None (Current selection)" semantics we want."""
        row = conn.execute(
            "SELECT default_template FROM tabs WHERE name = 'Main'"
        ).fetchone()
        assert row is not None, "Main is seeded by _initialize_default_tabs"
        assert row[0] is None

    def test_schema_version_advances_to_20(self, conn):
        row = conn.execute(
            "SELECT value_text FROM settings WHERE key='schema_version'"
        ).fetchone()
        assert int(row[0]) >= 20

    def test_second_pass_leaves_exactly_one_column(self, conn):
        """_ensure_schema is re-entered from scratch by tests; without the
        column-existence guard the second ALTER raises "duplicate column
        name", which the migration's except would swallow -- passing the test
        while logging a warning. Count the column instead of just not raising."""
        _schema_initialized_dbs.clear()
        _ensure_schema(conn)

        names = [c[1] for c in conn.execute("PRAGMA table_info(tabs)").fetchall()]
        assert names.count("default_template") == 1


# ---------------------------------------------------------------------------
# QueueStore.get_tab_default_template
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetTabDefaultTemplate:

    def test_returns_none_when_unset(self, store):
        assert store.get_tab_default_template("Main") is None

    def test_returns_stored_value(self, store):
        _set_default(store, "Main", "Nubiles")
        assert store.get_tab_default_template("Main") == "Nubiles"

    def test_empty_string_reads_as_none(self, store):
        """'' must never be written, but must read as equivalent to NULL so no
        caller has to remember the collapse."""
        with sqlite3.connect(store.db_path) as c:
            c.execute("UPDATE tabs SET default_template = '' WHERE name = 'Main'")
        assert store.get_tab_default_template("Main") is None

    def test_whitespace_reads_as_none(self, store):
        with sqlite3.connect(store.db_path) as c:
            c.execute("UPDATE tabs SET default_template = '   ' WHERE name = 'Main'")
        assert store.get_tab_default_template("Main") is None

    def test_unknown_tab_returns_none(self, store):
        """"All Tabs" is virtual and never a real row; an unknown name must
        return None rather than raise (load_items_by_tab models the same
        contract at database.py:1531-1535)."""
        assert store.get_tab_default_template("All Tabs") is None
        assert store.get_tab_default_template("NoSuchTab") is None

    def test_empty_name_returns_none(self, store):
        assert store.get_tab_default_template("") is None
        assert store.get_tab_default_template(None) is None

    def test_missing_column_returns_none(self, store):
        """A migration that fails is never retried: _run_migrations swallows
        every exception but _ensure_schema writes schema_version=20 anyway
        (database.py:211-215). So the read path must tolerate the column being
        absent and degrade to today's behaviour rather than raising."""
        with sqlite3.connect(store.db_path) as c:
            c.execute("ALTER TABLE tabs RENAME TO tabs_old")
            c.execute(
                "CREATE TABLE tabs ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  name TEXT NOT NULL UNIQUE,"
                "  tab_type TEXT NOT NULL DEFAULT 'user',"
                "  display_order INTEGER NOT NULL DEFAULT 0,"
                "  color_hint TEXT,"
                "  created_ts REAL,"
                "  updated_ts REAL,"
                "  is_active INTEGER NOT NULL DEFAULT 1"
                ")"
            )
            c.execute("INSERT INTO tabs(name, tab_type) VALUES('Main', 'system')")
            c.execute("DROP TABLE tabs_old")

        # Schema is already marked current, so no migration will re-add it.
        assert store.get_tab_default_template("Main") is None


# ---------------------------------------------------------------------------
# Resolution inside add_item
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAddItemResolvesTabDefault:
    """Asserted at the QueueManager level, not through the GUI -- this is the
    feature, and every live add path funnels through add_item."""

    @pytest.fixture
    def qm(self, store):
        """Real QueueStore behind a real QueueManager — a Mock store would
        return a truthy Mock from get_tab_default_template and silently
        invert the behaviour under test."""
        from unittest.mock import patch
        from src.storage.queue_manager import QueueManager
        with patch('src.storage.queue_manager.QueueStore', return_value=store):
            with patch('src.storage.queue_manager.QSettings'):
                mgr = QueueManager()
                yield mgr
                mgr._scan_worker_running = False

    @pytest.fixture
    def gallery(self, tmp_path):
        d = tmp_path / "gal"
        d.mkdir()
        (d / "a.jpg").write_bytes(b"x")
        return str(d)

    def test_tab_default_overrides_passed_template(self, qm, store, gallery):
        """The whole feature: the tab default beats an explicit argument."""
        _set_default(store, "Main", "Nubiles")

        qm.add_item(gallery, template_name="from_combo", tab_name="Main")

        assert qm.get_item(gallery).template_name == "Nubiles"

    def test_null_tab_default_leaves_passed_template_untouched(self, qm, gallery):
        qm.add_item(gallery, template_name="from_combo", tab_name="Main")
        assert qm.get_item(gallery).template_name == "from_combo"

    def test_empty_tab_default_behaves_like_null(self, qm, store, gallery):
        with sqlite3.connect(store.db_path) as c:
            c.execute("UPDATE tabs SET default_template = '' WHERE name = 'Main'")

        qm.add_item(gallery, template_name="from_combo", tab_name="Main")

        assert qm.get_item(gallery).template_name == "from_combo"

    def test_empty_passed_template_survives_null_default(self, qm, gallery):
        """Including '' -- we pass the caller's value through verbatim."""
        qm.add_item(gallery, template_name="", tab_name="Main")
        assert qm.get_item(gallery).template_name == ""

    def test_unknown_tab_name_does_not_raise(self, qm, gallery):
        result = qm.add_item(gallery, template_name="from_combo", tab_name="All Tabs")
        assert result
        assert qm.get_item(gallery).template_name == "from_combo"


# ---------------------------------------------------------------------------
# Rename regression
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenameKeepsDefault:

    def test_default_survives_rename_and_resolves_by_new_name(self, store):
        """Pins the name-keyed design. update_tab renames in place
        (UPDATE ... WHERE id = ?, database.py:1771) so the row id never
        changes -- but a future refactor of update_tab could silently break
        this, which is why it is a test and not a comment."""
        tab_id = store.create_tab("Shoots")
        _set_default(store, "Shoots", "Nubiles")

        store.update_tab(tab_id, name="Photosets")

        assert store.get_tab_default_template("Photosets") == "Nubiles"
        assert store.get_tab_default_template("Shoots") is None


# ---------------------------------------------------------------------------
# Guarantees that hold only because the relevant methods are untouched
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTabDefaultDoesNotReachOtherPaths:
    """These three are stated requirements, and each is currently satisfied
    only because the method involved never consults the tab default. Nothing
    structural stops a future change from wiring one up, so pin them."""

    def _row_template(self, store, path):
        with sqlite3.connect(store.db_path) as c:
            return c.execute(
                "SELECT template FROM galleries WHERE path = ?", (path,)
            ).fetchone()[0]

    def test_per_item_override_beats_the_tab_default(self, store, tmp_path):
        """The sharpest case: a user explicitly re-templating one gallery that
        sits in a tab which has a default set. The override must stick."""
        store.create_tab("Shoots")
        _set_default(store, "Shoots", "Nubiles")
        path = str(tmp_path / "g")
        store.bulk_upsert([{
            "path": path, "name": "g", "status": "queued",
            "template_name": "Nubiles", "tab_name": "Shoots",
        }])

        store.update_item_template(path, "Manual")

        assert self._row_template(store, path) == "Manual"

    def test_moving_into_a_tab_does_not_retemplate(self, store, tmp_path):
        """Moving an existing gallery into a tab with a default must leave its
        template alone -- move_galleries_to_tab writes tab_id/tab_name only."""
        store.create_tab("Shoots")
        _set_default(store, "Shoots", "Nubiles")
        path = str(tmp_path / "g")
        store.bulk_upsert([{
            "path": path, "name": "g", "status": "queued",
            "template_name": "Keepme", "tab_name": "Main",
        }])

        store.move_galleries_to_tab([path], "Shoots")

        assert self._row_template(store, path) == "Keepme"

    def test_restore_from_db_does_not_retemplate(self, store, tmp_path):
        """Reopening the app must not re-template galleries already in a tab
        that has since been given a default -- _dict_to_item reads the
        persisted value and never calls get_tab_default_template."""
        from unittest.mock import patch
        from src.storage.queue_manager import QueueManager

        store.create_tab("Shoots")
        # load_persistent_queue skips non-existent dirs unless completed.
        gdir = tmp_path / "g"
        gdir.mkdir()
        path = str(gdir)
        store.bulk_upsert([{
            "path": path, "name": "g", "status": "queued",
            "template_name": "Original", "tab_name": "Shoots",
        }])
        # Default set AFTER the gallery was already filed under that tab.
        _set_default(store, "Shoots", "Nubiles")

        with patch('src.storage.queue_manager.QueueStore', return_value=store), \
             patch('src.storage.queue_manager.QSettings'):
            qm = QueueManager()
            qm.load_persistent_queue()
            try:
                item = qm.get_item(path)
                assert item is not None, "gallery should be restored"
                assert item.template_name == "Original"
            finally:
                qm._scan_worker_running = False
