"""Tests for ForumPostDelegate (P3 Task 2)."""

import pytest
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from src.gui.delegates.forum_post_delegate import (
    ForumPostDelegate, format_cell_text,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_format_cell_text_for_each_status():
    assert "Posted" in format_cell_text(
        {"status": "posted", "posted_post_id": "555"}
    )
    assert "Stale" in format_cell_text(
        {"status": "stale", "posted_post_id": "555"}
    )
    assert "Failed" in format_cell_text(
        {"status": "failed", "posted_post_id": None}
    )
    assert "Queued" in format_cell_text(
        {"status": "queued", "posted_post_id": None}
    )
    assert format_cell_text(None) == ""


def test_delegate_creates_line_edit_editor(app):
    table = QTableWidget(1, 1)
    delegate = ForumPostDelegate(table)
    table.setItemDelegateForColumn(0, delegate)
    table.setItem(0, 0, QTableWidgetItem(""))
    idx = table.model().index(0, 0)
    editor = delegate.createEditor(table.viewport(), None, idx)
    assert editor is not None
    assert editor.metaObject().className() == "QLineEdit"


def test_delegate_emits_commit_text_on_set_model_data(app, qtbot=None):
    table = QTableWidget(1, 1)
    delegate = ForumPostDelegate(table)
    table.setItemDelegateForColumn(0, delegate)
    table.setItem(0, 0, QTableWidgetItem(""))
    idx = table.model().index(0, 0)

    received = []
    delegate.commit_text.connect(lambda r, t: received.append((r, t)))

    editor = delegate.createEditor(table.viewport(), None, idx)
    editor.setText("999999")
    delegate.setModelData(editor, table.model(), idx)

    assert received == [(0, "999999")]


def test_delegate_ignores_blank_commit(app):
    table = QTableWidget(1, 1)
    delegate = ForumPostDelegate(table)
    table.setItemDelegateForColumn(0, delegate)
    table.setItem(0, 0, QTableWidgetItem(""))
    idx = table.model().index(0, 0)

    received = []
    delegate.commit_text.connect(lambda r, t: received.append((r, t)))

    editor = delegate.createEditor(table.viewport(), None, idx)
    editor.setText("   ")
    delegate.setModelData(editor, table.model(), idx)

    assert received == []
