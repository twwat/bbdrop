"""QTextEdit with variable autocomplete triggered by the % key."""

from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtWidgets import QCompleter, QTextEdit


class AutoCompleteTextEdit(QTextEdit):
    """QTextEdit with variable autocomplete on % key"""

    def __init__(self, variables, parent=None):
        super().__init__(parent)
        self.variables = [(var, desc) for var, desc in variables if var]
        self.completer = None
        self.setup_completer()

    def setup_completer(self):
        # Create list of completion items with descriptions
        self.completion_items = [f"{var}  -  {desc}" for var, desc in self.variables]
        self.var_only = [var for var, _ in self.variables]

        model = QStringListModel(self.completion_items)
        self.completer = QCompleter(model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseSensitive)
        self.completer.activated.connect(self.insert_completion)

    def insert_completion(self, completion):
        """Insert the selected variable at cursor"""
        # Extract just the variable part (before the ' - ')
        var = completion.split('  -  ')[0]

        cursor = self.textCursor()

        # Remove the % and any partial text after it
        cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.KeepAnchor,
                            len(self.completer.completionPrefix()) + 1)
        cursor.removeSelectedText()

        # Insert the variable
        cursor.insertText(var)
        self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        # Handle completer popup navigation
        if self.completer and self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return,
                                Qt.Key.Key_Escape, Qt.Key.Key_Tab):
                event.ignore()
                return

        # Call parent to handle normal key input
        super().keyPressEvent(event)

        # Show completer when % is typed
        if event.text() == '%':
            self.show_completions('')
        # Update completer filter as user types after %
        elif self.completer and self.completer.popup().isVisible():
            # Get text after the last %
            cursor = self.textCursor()
            cursor.select(cursor.SelectionType.LineUnderCursor)
            line_text = cursor.selectedText()

            # Find the last % before cursor
            cursor_pos = self.textCursor().positionInBlock()
            last_percent = line_text.rfind('%', 0, cursor_pos)

            if last_percent >= 0:
                prefix = line_text[last_percent + 1:cursor_pos]
                self.show_completions(prefix)
            else:
                self.completer.popup().hide()

    def show_completions(self, prefix):
        """Show completion popup with filtered results"""
        self.completer.setCompletionPrefix(prefix)
        self.completer.complete()

        # Position popup at cursor
        cursor_rect = self.cursorRect()
        cursor_rect.setWidth(self.completer.popup().sizeHintForColumn(0)
                             + self.completer.popup().verticalScrollBar().sizeHint().width())
        self.completer.complete(cursor_rect)
