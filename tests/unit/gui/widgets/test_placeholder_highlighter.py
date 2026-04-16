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

    def test_placeholder_list_complete(self, qtbot):
        """All expected template placeholders are defined."""
        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        expected = [
            "#folderName#", "#width#", "#height#", "#longest#",
            "#extension#", "#pictureCount#", "#folderSize#",
            "#galleryLink#", "#allImages#", "#hostLinks#",
            "#custom1#", "#custom2#", "#custom3#", "#custom4#",
            "#ext1#", "#ext2#", "#ext3#", "#ext4#"
        ]
        for placeholder in expected:
            assert placeholder in highlighter.placeholders

    def test_highlight_block_with_placeholder(self, qtbot):
        """Highlighting placeholders doesn't alter text content."""
        doc = QTextDocument()
        PlaceholderHighlighter(doc)
        doc.setPlainText("Template with #folderName# placeholder")
        assert doc.toPlainText() == "Template with #folderName# placeholder"

    def test_highlight_block_with_conditional(self, qtbot):
        """Highlighting conditional tags doesn't alter text content."""
        doc = QTextDocument()
        PlaceholderHighlighter(doc)
        doc.setPlainText("[if folderName]Content[/if]")
        assert doc.toPlainText() == "[if folderName]Content[/if]"

    def test_highlight_block_with_link_format(self, qtbot):
        """Highlighting link-format placeholders doesn't alter text content."""
        doc = QTextDocument()
        PlaceholderHighlighter(doc)
        doc.setPlainText("[url=#link#]#hostName# - #partLabel# (#fileSize#)[/url]")
        assert doc.toPlainText() == "[url=#link#]#hostName# - #partLabel# (#fileSize#)[/url]"
