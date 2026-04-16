#!/usr/bin/env python3
"""Tests for BBCodeLinkFormatDialog."""

from src.gui.dialogs.bbcode_link_format_dialog import BBCodeLinkFormatDialog


class TestBBCodeLinkFormatDialog:
    """Test the BBCode link format editor dialog."""

    def test_dialog_creates(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "BBCode Link Format"

    def test_initial_text_set(self, qtbot):
        dialog = BBCodeLinkFormatDialog(initial_text="[url=#link#]#hostName#[/url]")
        qtbot.addWidget(dialog)
        assert dialog.editor.toPlainText() == "[url=#link#]#hostName#[/url]"

    def test_empty_initial_text(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        assert dialog.editor.toPlainText() == ""

    def test_get_text_returns_editor_content(self, qtbot):
        dialog = BBCodeLinkFormatDialog(initial_text="test")
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("[url=#link#]#hostName#[/url]")
        assert dialog.get_text() == "[url=#link#]#hostName#[/url]"

    def test_insert_placeholder_at_cursor(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("")
        dialog._insert_placeholder("#link#")
        assert dialog.editor.toPlainText() == "#link#"

    def test_insert_placeholder_appends_at_cursor_position(self, qtbot):
        dialog = BBCodeLinkFormatDialog(initial_text="hello ")
        qtbot.addWidget(dialog)
        # Move cursor to end
        cursor = dialog.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        dialog.editor.setTextCursor(cursor)
        dialog._insert_placeholder("#hostName#")
        assert dialog.editor.toPlainText() == "hello #hostName#"

    def test_preview_updates_on_text_change(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("[url=#link#]#hostName#[/url]")
        preview_text = dialog.preview_label.text()
        assert "https://example.com/file/abc123" in preview_text
        assert "Rapidgator" in preview_text

    def test_preview_shows_filesize(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("#hostName# (#fileSize#)")
        preview_text = dialog.preview_label.text()
        assert "250 MiB" in preview_text

    def test_preview_shows_part_placeholders(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("#hostName# - #partLabel# (#partNumber#/#partCount#)")
        preview_text = dialog.preview_label.text()
        assert "Part 1" in preview_text
        assert "1" in preview_text
        assert "2" in preview_text

    def test_all_six_placeholder_buttons_exist(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        assert len(dialog._placeholder_buttons) == 6

    def test_highlighter_attached(self, qtbot):
        dialog = BBCodeLinkFormatDialog()
        qtbot.addWidget(dialog)
        assert dialog.highlighter is not None
