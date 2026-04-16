#!/usr/bin/env python3
"""Tests for PlaceholderEditorDialog."""

from src.gui.dialogs.bbcode_link_format_dialog import PlaceholderEditorDialog, LINK_PLACEHOLDERS


# Custom placeholder list for testing parameterization
TEST_PLACEHOLDERS = [
    ("#name#", "Name", "A name", "Alice"),
    ("#value#", "Value", "A value", "42"),
]


class TestPlaceholderEditorDialog:
    """Test the generalized placeholder editor dialog."""

    def test_dialog_creates_with_defaults(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test Editor", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Test Editor"

    def test_custom_title(self, qtbot):
        dialog = PlaceholderEditorDialog(title="My Custom Title", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "My Custom Title"

    def test_initial_text_set(self, qtbot):
        dialog = PlaceholderEditorDialog(
            title="Test", placeholders=TEST_PLACEHOLDERS,
            initial_text="hello #name#"
        )
        qtbot.addWidget(dialog)
        assert dialog.editor.toPlainText() == "hello #name#"

    def test_empty_initial_text(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        assert dialog.editor.toPlainText() == ""

    def test_get_text_returns_editor_content(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("new content")
        assert dialog.get_text() == "new content"

    def test_insert_placeholder_at_cursor(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("")
        dialog._insert_placeholder("#name#")
        assert dialog.editor.toPlainText() == "#name#"

    def test_placeholder_buttons_match_count(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        assert len(dialog._placeholder_buttons) == 2

    def test_link_placeholders_create_six_buttons(self, qtbot):
        dialog = PlaceholderEditorDialog(
            title="BBCode Link Format", placeholders=LINK_PLACEHOLDERS
        )
        qtbot.addWidget(dialog)
        assert len(dialog._placeholder_buttons) == 6

    def test_preview_updates_on_text_change(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("Hello #name#, value=#value#")
        preview = dialog.preview_label.text()
        assert "Alice" in preview
        assert "42" in preview

    def test_preview_empty_shows_hint(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        dialog.editor.setPlainText("")
        assert "empty" in dialog.preview_label.text().lower()

    def test_highlighter_attached(self, qtbot):
        dialog = PlaceholderEditorDialog(title="Test", placeholders=TEST_PLACEHOLDERS)
        qtbot.addWidget(dialog)
        assert dialog.highlighter is not None
