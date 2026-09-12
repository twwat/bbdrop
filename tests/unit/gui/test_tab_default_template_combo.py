"""The Tab Settings dialog's "Default Template" combo.

Distinct from the per-destination Template: combos in the same panel --
those pick a forum-post BODY template (body_template_name); this one picks
the gallery BBCode template applied to newly added galleries.

The combo carries values in the data role, never the text. Template names
come from file stems (templates.py:140-152), so `None.txt` yields a
template named exactly "None", and "None (Current selection).txt" is a
legal Windows filename that collides with the sentinel's display text
character-for-character. Text comparison is therefore not safe here.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.widgets.tab_posting_config_panel import TabPostingConfigPanel
from src.storage.database import _ensure_schema, _schema_initialized_dbs

NONE_LABEL = "None (Current selection)"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    _ensure_schema(c)
    yield c
    c.close()
    _schema_initialized_dbs.discard(path)
    try:
        os.unlink(path)
    except OSError:
        pass


def _make_tab(conn) -> int:
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) VALUES('T','user',0)"
    )
    conn.commit()
    return conn.execute("SELECT id FROM tabs WHERE name='T'").fetchone()[0]


def _stored(conn, tab_id):
    return conn.execute(
        "SELECT default_template FROM tabs WHERE id = ?", (tab_id,)
    ).fetchone()[0]


def _templates(*names):
    """Patch load_templates in the panel's namespace."""
    return patch(
        "src.gui.widgets.tab_posting_config_panel.load_templates",
        return_value={n: "body" for n in names},
    )


@pytest.mark.unit
class TestDefaultTemplateCombo:

    def test_sentinel_is_first_and_carries_none(self, app, conn):
        tab_id = _make_tab(conn)
        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)

        combo = panel.default_template_combo
        assert combo.itemText(0) == NONE_LABEL
        assert combo.itemData(0) is None

    def test_defaults_to_sentinel_when_unset(self, app, conn):
        tab_id = _make_tab(conn)
        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)

        assert panel.default_template_combo.currentData() is None

    def test_templates_are_listed_with_data_role(self, app, conn):
        tab_id = _make_tab(conn)
        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)

        combo = panel.default_template_combo
        data = [combo.itemData(i) for i in range(combo.count())]
        assert data == [None, "default", "Nubiles"]

    def test_save_persists_selection(self, app, conn):
        tab_id = _make_tab(conn)
        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)
            idx = panel.default_template_combo.findData("Nubiles")
            panel.default_template_combo.setCurrentIndex(idx)
            assert panel.save()

        assert _stored(conn, tab_id) == "Nubiles"

    def test_save_sentinel_persists_null_not_display_text(self, app, conn):
        tab_id = _make_tab(conn)
        with sqlite3.connect(conn.execute("PRAGMA database_list").fetchone()[2]) as c:
            c.execute(
                "UPDATE tabs SET default_template = 'Nubiles' WHERE id = ?", (tab_id,)
            )

        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)
            panel.default_template_combo.setCurrentIndex(0)  # the sentinel
            assert panel.save()

        assert _stored(conn, tab_id) is None

    def test_round_trips_through_reload(self, app, conn):
        tab_id = _make_tab(conn)
        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)
            panel.default_template_combo.setCurrentIndex(
                panel.default_template_combo.findData("Nubiles")
            )
            assert panel.save()

            reloaded = TabPostingConfigPanel(conn, tab_id)

        assert reloaded.default_template_combo.currentData() == "Nubiles"

    def test_template_literally_named_none_is_distinct_from_sentinel(self, app, conn):
        """`None.txt` is a legal template. It must round-trip as the string
        "None" and stay distinguishable from the NULL sentinel."""
        tab_id = _make_tab(conn)
        with _templates("default", "None"):
            panel = TabPostingConfigPanel(conn, tab_id)
            combo = panel.default_template_combo

            idx = combo.findData("None")
            assert idx > 0, "the real template must not collapse onto the sentinel"
            combo.setCurrentIndex(idx)
            assert panel.save()

            assert _stored(conn, tab_id) == "None"

            reloaded = TabPostingConfigPanel(conn, tab_id)

        assert reloaded.default_template_combo.currentData() == "None"

    def test_template_named_like_the_sentinel_text_is_distinct(self, app, conn):
        """"None (Current selection).txt" is a legal filename. The sentinel is
        identified by its data role (None), so the real template still wins its
        own entry."""
        tab_id = _make_tab(conn)
        with _templates("default", NONE_LABEL):
            panel = TabPostingConfigPanel(conn, tab_id)
            combo = panel.default_template_combo

            idx = combo.findData(NONE_LABEL)
            assert idx > 0
            combo.setCurrentIndex(idx)
            assert panel.save()

        assert _stored(conn, tab_id) == NONE_LABEL


@pytest.mark.unit
class TestDeletedTemplateIsSurfaced:
    """A stale tab default is strictly worse than none: generate_bbcode_from_
    template silently falls back to "default" (templates.py:363-366), NOT to
    the quick-settings selection. So the dialog must not quietly show
    "None (Current selection)" while the database holds a dead name."""

    def test_missing_template_gets_its_own_marked_entry(self, app, conn):
        tab_id = _make_tab(conn)
        with sqlite3.connect(conn.execute("PRAGMA database_list").fetchone()[2]) as c:
            c.execute(
                "UPDATE tabs SET default_template = 'Deleted' WHERE id = ?", (tab_id,)
            )

        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)

        combo = panel.default_template_combo
        assert combo.currentData() == "Deleted", "must not silently snap to the sentinel"
        assert "deleted" in combo.currentText().lower()

    def test_saving_without_touching_it_preserves_the_stale_name(self, app, conn):
        """Opening the dialog and pressing Save must not destroy the setting."""
        tab_id = _make_tab(conn)
        with sqlite3.connect(conn.execute("PRAGMA database_list").fetchone()[2]) as c:
            c.execute(
                "UPDATE tabs SET default_template = 'Deleted' WHERE id = ?", (tab_id,)
            )

        with _templates("default", "Nubiles"):
            panel = TabPostingConfigPanel(conn, tab_id)
            assert panel.save()

        assert _stored(conn, tab_id) == "Deleted"
