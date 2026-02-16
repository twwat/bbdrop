"""Syntax highlighter for hook command templates with color-coded variables."""

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class CommandHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, hook_type=''):
        super().__init__(parent)

        # Define color formats for different variable types
        # Gallery info variables (blue/cyan)
        self.gallery_format = QTextCharFormat()
        self.gallery_format.setFontWeight(QFont.Weight.Bold)
        self.gallery_format.setForeground(QColor(41, 128, 185))  # Blue
        self.gallery_vars = ['%N', '%T', '%p', '%C', '%s', '%t']

        # Upload result variables (green)
        self.upload_format = QTextCharFormat()
        self.upload_format.setFontWeight(QFont.Weight.Bold)
        self.upload_format.setForeground(QColor(39, 174, 96))  # Green
        self.upload_vars = ['%g', '%j', '%b', '%z']

        # Ext field variables (orange)
        self.ext_format = QTextCharFormat()
        self.ext_format.setFontWeight(QFont.Weight.Bold)
        self.ext_format.setForeground(QColor(230, 126, 34))  # Orange
        self.ext_vars = ['%e1', '%e2', '%e3', '%e4']

        # Custom field variables (purple)
        self.custom_format = QTextCharFormat()
        self.custom_format.setFontWeight(QFont.Weight.Bold)
        self.custom_format.setForeground(QColor(142, 68, 173))  # Purple
        self.custom_vars = ['%c1', '%c2', '%c3', '%c4']

        # Build complete variable list sorted by length (longest first)
        all_vars = self.gallery_vars + self.upload_vars + self.ext_vars + self.custom_vars
        all_vars.sort(key=len, reverse=True)
        self.all_variables = all_vars

    def highlightBlock(self, text):
        # Highlight variables with color-coding
        for var in self.all_variables:
            # Determine which format to use
            if var in self.gallery_vars:
                var_format = self.gallery_format
            elif var in self.upload_vars:
                var_format = self.upload_format
            elif var in self.ext_vars:
                var_format = self.ext_format
            elif var in self.custom_vars:
                var_format = self.custom_format
            else:
                continue

            # Find and highlight all occurrences
            index = text.find(var)
            while index >= 0:
                self.setFormat(index, len(var), var_format)
                index = text.find(var, index + len(var))
