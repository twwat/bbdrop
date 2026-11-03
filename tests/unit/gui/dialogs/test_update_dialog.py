"""Tests for the update-available dialog's release notes rendering."""

import re

import pytest

from src.gui.dialogs.update_dialog import (
    UpdateDialog, _format_release_date, _link_bare_urls,
)

pytestmark = pytest.mark.unit

NOTES = """## Release v0.9.10

### What's New

- **Editable Discord messages** — each event has its own template

**Full Changelog**: https://github.com/twwat/bbdrop/compare/v0.9.9...v0.9.10
"""


@pytest.fixture
def dialog(qtbot):
    d = UpdateDialog(None, "0.9.9", "0.9.10",
                     "https://github.com/twwat/bbdrop/releases/tag/v0.9.10",
                     NOTES, "2026-11-03T14:22:05Z")
    qtbot.addWidget(d)
    return d


def test_release_notes_render_as_markdown_not_raw_text(dialog):
    viewer = dialog._notes_viewer
    plain = viewer.toPlainText()
    assert "##" not in plain
    assert "**" not in plain
    assert "Editable Discord messages" in plain
    html = viewer.toHtml()
    assert "<h2" in html


def test_full_changelog_url_is_linked_whole(dialog):
    hrefs = re.findall(r'href="([^"]+)"', dialog._notes_viewer.toHtml())
    assert hrefs == ["https://github.com/twwat/bbdrop/compare/v0.9.9...v0.9.10"]


def test_links_open_in_browser(dialog):
    assert dialog._notes_viewer.openExternalLinks()


def test_empty_release_body_does_not_crash(qtbot):
    # GitHub sends "body": null for a release with no notes.
    d = UpdateDialog(None, "0.9.9", "0.9.10", "https://example.invalid", None, "")
    qtbot.addWidget(d)
    assert d._notes_viewer.toPlainText() == ""


def test_release_date_is_human_readable():
    assert _format_release_date("2026-11-03T14:22:05Z") == "November 3, 2026"
    assert _format_release_date("not a date") == "not a date"
    assert _format_release_date("") == ""


@pytest.mark.parametrize("text, expected", [
    ("see https://x.com/a.", "see <https://x.com/a>."),
    ("[t](https://x.com/b)", "[t](https://x.com/b)"),
    ("<https://x.com/c>", "<https://x.com/c>"),
    ("https://g.com/compare/v1...v2", "<https://g.com/compare/v1...v2>"),
])
def test_link_bare_urls(text, expected):
    assert _link_bare_urls(text) == expected
