#!/usr/bin/env python3
"""Tests for the shared PlaceholderHighlighter widget."""

import pytest
from PyQt6.QtGui import QTextDocument

from src.gui.widgets.placeholder_highlighter import PlaceholderHighlighter


class TestPlaceholderHighlighter:
    """Test syntax highlighting for template and link-format placeholders."""

    def test_highlighter_initialization(self, qtbot):
        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        assert highlighter.placeholder_format is not None
        assert highlighter.conditional_format is not None
        assert len(highlighter.placeholders) > 0

    def test_template_placeholders_present(self, qtbot):
        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        for p in ["#folderName#", "#allImages#", "#hostLinks#", "#cover#"]:
            assert p in highlighter.placeholders

    def test_link_format_placeholders_present(self, qtbot):
        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        for p in ["#link#", "#hostName#", "#fileSize#", "#partLabel#", "#partNumber#", "#partCount#"]:
            assert p in highlighter.placeholders

    def test_conditional_tags_present(self, qtbot):
        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        assert "[if" in highlighter.conditional_tags
        assert "[else]" in highlighter.conditional_tags
        assert "[/if]" in highlighter.conditional_tags

    def test_highlight_block_runs_without_error(self, qtbot):
        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)
        doc.setPlainText("[url=#link#]#hostName# - #partLabel# (#fileSize#)[/url]")
        # Highlighter runs automatically on setPlainText; no crash = pass
