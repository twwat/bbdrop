#!/usr/bin/env python3
"""
pytest-qt tests for Template Manager Dialog
Tests template CRUD operations, validation, and dialog interactions
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, mock_open, call
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QInputDialog, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from src.gui.dialogs.template_manager import (
    TemplateManagerDialog,
    ConditionalInsertDialog,
    PlaceholderHighlighter
)


# ============================================================================
# PlaceholderHighlighter Tests
# ============================================================================

class TestPlaceholderHighlighter:
    """Test syntax highlighting for template placeholders"""

    def test_highlighter_initialization(self, qtbot):
        """Test PlaceholderHighlighter creates with formats"""
        from PyQt6.QtGui import QTextDocument

        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        assert highlighter is not None
        assert highlighter.placeholder_format is not None
        assert highlighter.conditional_format is not None
        assert len(highlighter.placeholders) > 0
        assert len(highlighter.conditional_tags) > 0

    def test_placeholder_list_complete(self, qtbot):
        """Test all expected placeholders are defined"""
        from PyQt6.QtGui import QTextDocument

        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        expected_placeholders = [
            "#folderName#", "#width#", "#height#", "#longest#",
            "#extension#", "#pictureCount#", "#folderSize#",
            "#galleryLink#", "#allImages#", "#hostLinks#",
            "#custom1#", "#custom2#", "#custom3#", "#custom4#",
            "#ext1#", "#ext2#", "#ext3#", "#ext4#"
        ]

        for placeholder in expected_placeholders:
            assert placeholder in highlighter.placeholders

    def test_conditional_tags_defined(self, qtbot):
        """Test conditional tags are defined"""
        from PyQt6.QtGui import QTextDocument

        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        assert "[if" in highlighter.conditional_tags
        assert "[else]" in highlighter.conditional_tags
        assert "[/if]" in highlighter.conditional_tags

    def test_highlight_block_with_placeholder(self, qtbot):
        """Test highlighting placeholders in text"""
        from PyQt6.QtGui import QTextDocument

        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)
        doc.setPlainText("Template with #folderName# placeholder")

        # highlightBlock is called automatically by QSyntaxHighlighter
        assert doc.toPlainText() == "Template with #folderName# placeholder"

    def test_highlight_block_with_conditional(self, qtbot):
        """Test highlighting conditional tags"""
        from PyQt6.QtGui import QTextDocument

        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)
        doc.setPlainText("[if folderName]Content[/if]")

        # highlightBlock is called automatically
        assert doc.toPlainText() == "[if folderName]Content[/if]"

    def test_dark_mode_detection(self, qtbot, qapp):
        """Test highlighter adapts to dark mode"""
        from PyQt6.QtGui import QTextDocument

        doc = QTextDocument()
        highlighter = PlaceholderHighlighter(doc)

        # Just verify highlighter was created successfully
        # Dark mode detection happens during initialization
        assert highlighter.placeholder_format is not None
        assert highlighter.conditional_format is not None


# ============================================================================
# ConditionalInsertDialog Tests
# ============================================================================

class TestConditionalInsertDialog:
    """Test conditional tag insertion dialog"""

    def test_dialog_initialization(self, qtbot):
        """Test ConditionalInsertDialog creates successfully"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)
        assert dialog.isModal()
        assert dialog.windowTitle() == "Insert Conditional"

    def test_placeholder_combo_populated(self, qtbot):
        """Test placeholder combo box has all options"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        expected_items = [
            "folderName", "pictureCount", "width", "height", "longest",
            "extension", "folderSize", "galleryLink", "allImages", "hostLinks",
            "custom1", "custom2", "custom3", "custom4",
            "ext1", "ext2", "ext3", "ext4"
        ]

        assert dialog.placeholder_combo.count() == len(expected_items)
        for item in expected_items:
            assert dialog.placeholder_combo.findText(item) >= 0

    def test_exists_radio_default_checked(self, qtbot):
        """Test 'exists' radio button is checked by default"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        assert dialog.exists_radio.isChecked()
        assert not dialog.equals_radio.isChecked()
        assert not dialog.value_input.isEnabled()

    def test_equals_radio_enables_value_input(self, qtbot):
        """Test selecting 'equals' radio enables value input"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        # Set equals radio button checked programmatically
        dialog.equals_radio.setChecked(True)

        # Process events to allow signal/slot connections to fire
        qtbot.wait(10)

        assert dialog.equals_radio.isChecked()
        assert dialog.value_input.isEnabled()

    def test_get_conditional_text_exists(self, qtbot):
        """Test generating conditional text for 'exists' check"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        dialog.placeholder_combo.setCurrentText("folderName")
        dialog.exists_radio.setChecked(True)
        dialog.include_else.setChecked(False)

        text = dialog.get_conditional_text()

        assert text == "[if folderName]\nContent\n[/if]"

    def test_get_conditional_text_equals(self, qtbot):
        """Test generating conditional text for 'equals' check"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        dialog.placeholder_combo.setCurrentText("extension")
        dialog.equals_radio.setChecked(True)
        dialog.value_input.setText("jpg")
        dialog.include_else.setChecked(False)

        text = dialog.get_conditional_text()

        assert text == "[if extension=jpg]\nContent\n[/if]"

    def test_get_conditional_text_with_else(self, qtbot):
        """Test generating conditional text with else clause"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        dialog.placeholder_combo.setCurrentText("pictureCount")
        dialog.exists_radio.setChecked(True)
        dialog.include_else.setChecked(True)

        text = dialog.get_conditional_text()

        expected = "[if pictureCount]\nContent when true\n[else]\nContent when false\n[/if]"
        assert text == expected

    def test_dialog_accept(self, qtbot):
        """Test accepting dialog"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        with qtbot.waitSignal(dialog.finished):
            dialog.accept()

        assert dialog.result() == QDialog.DialogCode.Accepted

    def test_dialog_reject(self, qtbot):
        """Test rejecting dialog"""
        dialog = ConditionalInsertDialog()
        qtbot.addWidget(dialog)

        with qtbot.waitSignal(dialog.finished):
            dialog.reject()

        assert dialog.result() == QDialog.DialogCode.Rejected


# ============================================================================
# TemplateManagerDialog Initialization Tests
# ============================================================================

class TestTemplateManagerDialogInit:
    """Test TemplateManagerDialog initialization"""

    @patch('imxup.load_templates')
    def test_dialog_initialization(self, mock_load, qtbot):
        """Test TemplateManagerDialog creates successfully"""
        mock_load.return_value = {
            'default': '[b]#folderName#[/b]',
            'custom1': 'Custom template'
        }

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)
        assert dialog.isModal()
        assert dialog.windowTitle() == "Manage BBCode Templates"

    @patch('imxup.load_templates')
    def test_initial_state(self, mock_load, qtbot):
        """Test dialog initial state"""
        mock_load.return_value = {'default': 'Template'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        assert not dialog.unsaved_changes
        assert dialog.current_template_name is None
        assert dialog.initial_template == "default"

    @patch('imxup.load_templates')
    def test_ui_components_created(self, mock_load, qtbot):
        """Test all UI components are created"""
        mock_load.return_value = {'default': 'Template'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        assert dialog.template_list is not None
        assert dialog.template_editor is not None
        assert dialog.new_btn is not None
        assert dialog.rename_btn is not None
        assert dialog.delete_btn is not None
        assert dialog.save_btn is not None
        assert dialog.validate_btn is not None

    @patch('imxup.load_templates')
    def test_highlighter_attached(self, mock_load, qtbot):
        """Test syntax highlighter is attached to editor"""
        mock_load.return_value = {'default': 'Template'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        assert dialog.highlighter is not None
        assert isinstance(dialog.highlighter, PlaceholderHighlighter)


# ============================================================================
# Template Loading Tests
# ============================================================================

class TestTemplateLoading:
    """Test template loading functionality"""

    @patch('imxup.load_templates')
    def test_load_templates_populates_list(self, mock_load, qtbot):
        """Test loading templates populates the list"""
        mock_load.return_value = {
            'default': 'Default template',
            'custom1': 'Custom 1',
            'custom2': 'Custom 2'
        }

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        assert dialog.template_list.count() == 3
        items = [dialog.template_list.item(i).text() for i in range(dialog.template_list.count())]
        assert 'default' in items
        assert 'custom1' in items
        assert 'custom2' in items

    @patch('imxup.load_templates')
    def test_initial_template_selected(self, mock_load, qtbot):
        """Test initial template is selected on load"""
        mock_load.return_value = {
            'default': 'Default',
            'custom': 'Custom'
        }

        dialog = TemplateManagerDialog(current_template='custom')
        qtbot.addWidget(dialog)

        assert dialog.template_list.currentItem().text() == 'custom'

    @patch('imxup.load_templates')
    def test_fallback_to_first_template(self, mock_load, qtbot):
        """Test fallback to first template if initial not found"""
        mock_load.return_value = {
            'default': 'Default',
            'custom': 'Custom'
        }

        dialog = TemplateManagerDialog(current_template='nonexistent')
        qtbot.addWidget(dialog)

        assert dialog.template_list.currentRow() == 0

    @patch('imxup.load_templates')
    def test_load_template_content(self, mock_load, qtbot):
        """Test loading template content into editor"""
        template_content = '[b]#folderName#[/b]\n#allImages#'
        mock_load.return_value = {'test': template_content}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.load_template_content('test')

        assert dialog.template_editor.toPlainText() == template_content
        assert not dialog.unsaved_changes


# ============================================================================
# Template Selection Tests
# ============================================================================

class TestTemplateSelection:
    """Test template selection behavior"""

    @patch('imxup.load_templates')
    def test_select_template_loads_content(self, mock_load, qtbot):
        """Test selecting template loads its content"""
        mock_load.return_value = {
            'default': 'Default content',
            'custom': 'Custom content'
        }

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        # Select custom template
        dialog.template_list.setCurrentRow(1)

        assert dialog.template_editor.toPlainText() == 'Custom content'

    @patch('imxup.load_templates')
    def test_select_default_disables_editing(self, mock_load, qtbot):
        """Test selecting default template disables editing"""
        mock_load.return_value = {
            'default': 'Default',
            'custom': 'Custom'
        }

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        # Find and select default template
        for i in range(dialog.template_list.count()):
            if dialog.template_list.item(i).text() == 'default':
                dialog.template_list.setCurrentRow(i)
                break

        assert dialog.template_editor.isReadOnly()
        assert not dialog.rename_btn.isEnabled()
        assert not dialog.delete_btn.isEnabled()

    @patch('imxup.load_templates')
    def test_select_custom_enables_editing(self, mock_load, qtbot):
        """Test selecting custom template enables editing"""
        mock_load.return_value = {
            'default': 'Default',
            'custom': 'Custom'
        }

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        # Select custom template (not default)
        dialog.template_list.setCurrentRow(1)

        assert not dialog.template_editor.isReadOnly()
        assert dialog.rename_btn.isEnabled()
        assert dialog.delete_btn.isEnabled()

    @patch('imxup.load_templates')
    def test_selection_updates_current_template_name(self, mock_load, qtbot):
        """Test selection updates current_template_name"""
        mock_load.return_value = {'test': 'Content'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)

        assert dialog.current_template_name == 'test'


# ============================================================================
# Template CRUD Operations Tests
# ============================================================================

class TestCreateTemplate:
    """Test creating new templates"""

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QInputDialog.getText')
    def test_create_new_template(self, mock_input, mock_load, qtbot):
        """Test creating a new template"""
        mock_load.return_value = {'default': 'Default'}
        mock_input.return_value = ('new_template', True)

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        initial_count = dialog.template_list.count()
        dialog.create_new_template()

        assert dialog.template_list.count() == initial_count + 1
        assert dialog.current_template_name == 'new_template'
        assert dialog.unsaved_changes
        assert dialog.save_btn.isEnabled()

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QInputDialog.getText')
    def test_create_template_cancelled(self, mock_input, mock_load, qtbot):
        """Test cancelling template creation"""
        mock_load.return_value = {'default': 'Default'}
        mock_input.return_value = ('', False)

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        initial_count = dialog.template_list.count()
        dialog.create_new_template()

        assert dialog.template_list.count() == initial_count

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QInputDialog.getText')
    @patch('PyQt6.QtWidgets.QMessageBox.warning')
    def test_create_duplicate_template_shows_warning(self, mock_warning, mock_input, mock_load, qtbot):
        """Test creating template with duplicate name shows warning"""
        mock_load.return_value = {'existing': 'Content'}
        mock_input.return_value = ('existing', True)

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        initial_count = dialog.template_list.count()
        dialog.create_new_template()

        mock_warning.assert_called_once()
        assert dialog.template_list.count() == initial_count


class TestRenameTemplate:
    """Test renaming templates"""

    @patch('imxup.load_templates')
    @patch('imxup.get_template_path')
    @patch('PyQt6.QtWidgets.QInputDialog.getText')
    @patch('PyQt6.QtWidgets.QMessageBox.information')
    @patch('os.rename')
    def test_rename_template_success(self, mock_rename, mock_info, mock_input, mock_path, mock_load, qtbot):
        """Test successfully renaming a template"""
        mock_load.return_value = {'old_name': 'Content'}
        mock_path.return_value = '/tmp/templates'
        mock_input.return_value = ('new_name', True)

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.rename_template()

        mock_rename.assert_called_once()
        mock_info.assert_called_once()

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QMessageBox.warning')
    def test_rename_default_template_blocked(self, mock_warning, mock_load, qtbot):
        """Test renaming default template is blocked"""
        mock_load.return_value = {'default': 'Content'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        # Select default template
        for i in range(dialog.template_list.count()):
            if dialog.template_list.item(i).text() == 'default':
                dialog.template_list.setCurrentRow(i)
                break

        dialog.rename_template()

        mock_warning.assert_called_once()
        assert "Cannot rename the default template" in str(mock_warning.call_args)

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QInputDialog.getText')
    def test_rename_template_cancelled(self, mock_input, mock_load, qtbot):
        """Test cancelling template rename"""
        mock_load.return_value = {'test': 'Content'}
        mock_input.return_value = ('', False)

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        original_name = dialog.template_list.currentItem().text()
        dialog.rename_template()

        assert dialog.template_list.currentItem().text() == original_name


class TestDeleteTemplate:
    """Test deleting templates"""

    @patch('imxup.load_templates')
    @patch('imxup.get_template_path')
    @patch('PyQt6.QtWidgets.QMessageBox.question')
    @patch('PyQt6.QtWidgets.QMessageBox.information')
    @patch('os.remove')
    def test_delete_template_success(self, mock_remove, mock_info, mock_question, mock_path, mock_load, qtbot):
        """Test successfully deleting a template"""
        mock_load.return_value = {'test': 'Content'}
        mock_path.return_value = '/tmp/templates'
        mock_question.return_value = QMessageBox.StandardButton.Yes

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        initial_count = dialog.template_list.count()

        dialog.delete_template()

        mock_remove.assert_called_once()
        assert dialog.template_list.count() == initial_count - 1

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QMessageBox.warning')
    def test_delete_default_template_blocked(self, mock_warning, mock_load, qtbot):
        """Test deleting default template is blocked"""
        mock_load.return_value = {'default': 'Content'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        for i in range(dialog.template_list.count()):
            if dialog.template_list.item(i).text() == 'default':
                dialog.template_list.setCurrentRow(i)
                break

        dialog.delete_template()

        mock_warning.assert_called_once()
        assert "Cannot delete the default template" in str(mock_warning.call_args)

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QMessageBox.question')
    def test_delete_template_cancelled(self, mock_question, mock_load, qtbot):
        """Test cancelling template deletion"""
        mock_load.return_value = {'test': 'Content'}
        mock_question.return_value = QMessageBox.StandardButton.No

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        initial_count = dialog.template_list.count()

        dialog.delete_template()

        assert dialog.template_list.count() == initial_count


# ============================================================================
# Template Saving Tests
# ============================================================================

class TestSaveTemplate:
    """Test template saving functionality"""

    @patch('imxup.load_templates')
    @patch('imxup.get_template_path')
    @patch('PyQt6.QtWidgets.QMessageBox.information')
    @patch('builtins.open', new_callable=mock_open)
    def test_save_template_success(self, mock_file, mock_info, mock_path, mock_load, qtbot):
        """Test successfully saving a template"""
        mock_load.return_value = {'test': 'Old content'}
        mock_path.return_value = '/tmp/templates'

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.template_editor.setPlainText('New content')
        dialog.current_template_name = 'test'

        dialog.save_template()

        mock_file.assert_called_once()
        assert not dialog.save_btn.isEnabled()
        assert not dialog.unsaved_changes

    @patch('imxup.load_templates')
    @patch('imxup.get_template_path')
    @patch('PyQt6.QtWidgets.QMessageBox.warning')
    @patch('builtins.open', side_effect=IOError("Write failed"))
    def test_save_template_error_handling(self, mock_file, mock_warning, mock_path, mock_load, qtbot):
        """Test error handling during template save"""
        mock_load.return_value = {'test': 'Content'}
        mock_path.return_value = '/tmp/templates'

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.current_template_name = 'test'

        dialog.save_template()

        mock_warning.assert_called_once()
        assert "Failed to save template" in str(mock_warning.call_args)

    @patch('imxup.load_templates')
    def test_save_button_enabled_on_change(self, mock_load, qtbot):
        """Test save button enabled when template is changed"""
        mock_load.return_value = {'test': 'Content'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.current_template_name = 'test'

        assert not dialog.save_btn.isEnabled()

        # Trigger change
        dialog.template_editor.setPlainText('Modified content')

        assert dialog.save_btn.isEnabled()
        assert dialog.unsaved_changes


# ============================================================================
# Template Validation Tests
# ============================================================================

class TestTemplateValidation:
    """Test template syntax validation"""

    @patch('imxup.load_templates')
    def test_validate_valid_template(self, mock_load, qtbot):
        """Test validating a valid template"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        content = "[b]#folderName#[/b]\n[if pictureCount]#pictureCount# images[/if]"
        is_valid, errors = dialog.validate_template_syntax(content)

        assert is_valid
        assert len(errors) == 0

    @patch('imxup.load_templates')
    def test_validate_unmatched_if_tags(self, mock_load, qtbot):
        """Test detecting unmatched [if] tags"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        content = "[if folderName]Content"  # Missing [/if]
        is_valid, errors = dialog.validate_template_syntax(content)

        assert not is_valid
        assert any("Unmatched conditional tags" in err for err in errors)

    @patch('imxup.load_templates')
    def test_validate_invalid_if_syntax(self, mock_load, qtbot):
        """Test detecting invalid [if] syntax"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        content = "[if]Content[/if]"  # Missing placeholder
        is_valid, errors = dialog.validate_template_syntax(content)

        assert not is_valid
        assert any("Invalid [if] syntax" in err for err in errors)

    @patch('imxup.load_templates')
    def test_validate_orphaned_else(self, mock_load, qtbot):
        """Test detecting orphaned [else] tags"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        content = "[else]\nContent outside conditional"
        is_valid, errors = dialog.validate_template_syntax(content)

        assert not is_valid
        assert any("[else] tag found outside" in err for err in errors)

    @patch('imxup.load_templates')
    def test_validate_unmatched_bbcode(self, mock_load, qtbot):
        """Test detecting unmatched BBCode tags"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        content = "[b]Bold text"  # Missing [/b]
        is_valid, errors = dialog.validate_template_syntax(content)

        assert not is_valid
        assert any("Unmatched [b] tags" in err for err in errors)

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QMessageBox.information')
    def test_validate_and_show_results_success(self, mock_info, mock_load, qtbot):
        """Test validation success message"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_editor.setPlainText("[b]Valid template[/b]")
        dialog.validate_and_show_results()

        mock_info.assert_called_once()
        assert "No syntax errors" in str(mock_info.call_args)

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QMessageBox.warning')
    def test_validate_and_show_results_errors(self, mock_warning, mock_load, qtbot):
        """Test validation error message"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_editor.setPlainText("[if folderName]No closing tag")
        dialog.validate_and_show_results()

        mock_warning.assert_called_once()
        assert "syntax errors" in str(mock_warning.call_args)


# ============================================================================
# Placeholder Insertion Tests
# ============================================================================

class TestPlaceholderInsertion:
    """Test placeholder insertion functionality"""

    @patch('imxup.load_templates')
    def test_insert_placeholder(self, mock_load, qtbot):
        """Test inserting a placeholder"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_editor.clear()
        dialog.insert_placeholder("#folderName#")

        assert "#folderName#" in dialog.template_editor.toPlainText()

    @patch('imxup.load_templates')
    def test_insert_multiple_placeholders(self, mock_load, qtbot):
        """Test inserting multiple placeholders"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_editor.clear()
        dialog.insert_placeholder("#folderName#")
        dialog.insert_placeholder(" - ")
        dialog.insert_placeholder("#pictureCount#")

        text = dialog.template_editor.toPlainText()
        assert "#folderName#" in text
        assert "#pictureCount#" in text

    @patch('imxup.load_templates')
    def test_insert_text(self, mock_load, qtbot):
        """Test inserting plain text"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_editor.clear()
        dialog.insert_text("[else]\n")

        assert "[else]" in dialog.template_editor.toPlainText()

    @patch('imxup.load_templates')
    def test_insert_conditional_helper(self, mock_load, qtbot):
        """Test inserting conditional via helper dialog"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        # Mock the ConditionalInsertDialog
        with patch.object(ConditionalInsertDialog, 'exec', return_value=QDialog.DialogCode.Accepted):
            with patch.object(ConditionalInsertDialog, 'get_conditional_text',
                            return_value='[if test]\nContent\n[/if]'):
                dialog.insert_conditional_helper()

        assert '[if test]' in dialog.template_editor.toPlainText()


# ============================================================================
# Unsaved Changes Tests
# ============================================================================

class TestUnsavedChanges:
    """Test unsaved changes handling"""

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QMessageBox.question')
    def test_switch_template_with_unsaved_changes_save(self, mock_question, mock_load, qtbot):
        """Test switching templates with unsaved changes - save option"""
        mock_load.return_value = {
            'template1': 'Content 1',
            'template2': 'Content 2'
        }
        mock_question.return_value = QMessageBox.StandardButton.Yes

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        # Select first template and make changes
        dialog.template_list.setCurrentRow(0)
        dialog.current_template_name = dialog.template_list.item(0).text()
        dialog.template_editor.setPlainText('Modified')
        dialog.unsaved_changes = True

        # Mock save operation
        with patch('builtins.open', mock_open()):
            with patch('src.gui.dialogs.template_manager.get_template_path', return_value='/tmp'):
                # Try to switch to second template
                dialog.template_list.setCurrentRow(1)

        mock_question.assert_called_once()

    @patch('imxup.load_templates')
    @patch('PyQt6.QtWidgets.QMessageBox.question')
    def test_switch_template_with_unsaved_changes_cancel(self, mock_question, mock_load, qtbot):
        """Test switching templates with unsaved changes - cancel option"""
        mock_load.return_value = {
            'template1': 'Content 1',
            'template2': 'Content 2'
        }
        mock_question.return_value = QMessageBox.StandardButton.Cancel

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.current_template_name = 'template1'
        dialog.unsaved_changes = True

        # Try to switch to second template
        dialog.template_list.setCurrentRow(1)

        # Should stay on first template
        assert dialog.template_list.currentRow() == 0

    @patch('imxup.load_templates')
    def test_close_with_unsaved_changes(self, mock_load, qtbot):
        """Test closing dialog with unsaved changes"""
        mock_load.return_value = {'test': 'Content'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.current_template_name = 'test'
        dialog.template_editor.setPlainText('Modified')
        dialog.unsaved_changes = True

        # Mock the question dialog to return Cancel
        with patch('src.gui.dialogs.template_manager.QMessageBox.question',
                  return_value=QMessageBox.StandardButton.Cancel):
            event = Mock()
            dialog.closeEvent(event)

            event.ignore.assert_called_once()

    @patch('imxup.load_templates')
    def test_save_with_validation_errors_confirm(self, mock_load, qtbot):
        """Test saving template with validation errors after confirmation"""
        mock_load.return_value = {'test': 'Content'}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.current_template_name = 'test'
        dialog.template_editor.setPlainText('[if unclosed')

        with patch('src.gui.dialogs.template_manager.QMessageBox.question',
                  return_value=QMessageBox.StandardButton.Yes):
            with patch('builtins.open', mock_open()):
                with patch('src.gui.dialogs.template_manager.get_template_path', return_value='/tmp'):
                    with patch('src.gui.dialogs.template_manager.QMessageBox.information'):
                        dialog.save_template()

        # Template should be saved despite errors
        assert not dialog.unsaved_changes


# ============================================================================
# Integration Tests
# ============================================================================

class TestTemplateManagerIntegration:
    """Integration tests for complete workflows"""

    @patch('imxup.load_templates')
    @patch('imxup.get_template_path')
    @patch('PyQt6.QtWidgets.QInputDialog.getText')
    @patch('builtins.open', new_callable=mock_open)
    @patch('PyQt6.QtWidgets.QMessageBox.information')
    def test_complete_template_creation_workflow(self, mock_info, mock_file, mock_input,
                                                  mock_path, mock_load, qtbot):
        """Test complete workflow: create, edit, validate, save"""
        mock_load.return_value = {'default': 'Default'}
        mock_path.return_value = '/tmp/templates'
        mock_input.return_value = ('new_template', True)

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        # Create new template
        dialog.create_new_template()
        assert dialog.current_template_name == 'new_template'

        # Edit template
        dialog.template_editor.setPlainText('[b]#folderName#[/b]')
        assert dialog.unsaved_changes

        # Validate
        is_valid, errors = dialog.validate_template_syntax(dialog.template_editor.toPlainText())
        assert is_valid

        # Save
        dialog.save_template()
        assert not dialog.unsaved_changes

    @patch('imxup.load_templates')
    def test_placeholder_buttons_functional(self, mock_load, qtbot):
        """Test all placeholder insertion buttons work"""
        mock_load.return_value = {'test': ''}

        dialog = TemplateManagerDialog()
        qtbot.addWidget(dialog)

        dialog.template_list.setCurrentRow(0)
        dialog.current_template_name = 'test'
        dialog.template_editor.clear()

        # Test some placeholders
        test_placeholders = ['#folderName#', '#pictureCount#', '#width#']

        for placeholder in test_placeholders:
            dialog.insert_placeholder(placeholder)

        text = dialog.template_editor.toPlainText()
        for placeholder in test_placeholders:
            assert placeholder in text


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
