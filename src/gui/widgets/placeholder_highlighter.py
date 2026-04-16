"""Reusable syntax highlighter for #placeholder# patterns and conditional tags."""

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont


class PlaceholderHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for BBCode template placeholders and conditional tags"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Detect dark mode
        palette = QApplication.palette()
        is_dark = palette.window().color().lightness() < 128

        # Placeholder format
        self.placeholder_format = QTextCharFormat()
        if is_dark:
            self.placeholder_format.setBackground(QColor("#5c4a1f"))
            self.placeholder_format.setForeground(QColor("#ffd966"))
        else:
            self.placeholder_format.setBackground(QColor("#fff3cd"))
            self.placeholder_format.setForeground(QColor("#856404"))
        self.placeholder_format.setFontWeight(QFont.Weight.Bold)

        # Conditional tag format
        self.conditional_format = QTextCharFormat()
        if is_dark:
            self.conditional_format.setBackground(QColor("#1a3d4d"))
            self.conditional_format.setForeground(QColor("#66ccff"))
        else:
            self.conditional_format.setBackground(QColor("#d1ecf1"))
            self.conditional_format.setForeground(QColor("#0c5460"))
        self.conditional_format.setFontWeight(QFont.Weight.Bold)

        # Define all placeholders (generic #word# pattern matching)
        self.placeholders = [
            "#folderName#", "#width#", "#height#", "#longest#",
            "#extension#", "#pictureCount#", "#folderSize#",
            "#galleryLink#", "#allImages#", "#hostLinks#", "#cover#",
            "#custom1#", "#custom2#", "#custom3#", "#custom4#",
            "#ext1#", "#ext2#", "#ext3#", "#ext4#",
            "#link#", "#hostName#", "#fileSize#",
            "#partLabel#", "#partNumber#", "#partCount#",
            "#filename#", "#duration#", "#resolution#",
            "#fps#", "#bitrate#", "#videoCodec#", "#audioCodec#",
            "#audioTracks#", "#audioTrack1#", "#audioTrack2#",
            "#filesize#",
        ]

        # Conditional tags
        self.conditional_tags = ["[if", "[else]", "[/if]"]

    def highlightBlock(self, text):
        """Highlight placeholders and conditional tags in the text block"""
        # Highlight placeholders
        for placeholder in self.placeholders:
            index = 0
            while True:
                index = text.find(placeholder, index)
                if index == -1:
                    break
                self.setFormat(index, len(placeholder), self.placeholder_format)
                index += len(placeholder)

        # Highlight conditional tags
        for tag in self.conditional_tags:
            index = 0
            while True:
                index = text.find(tag, index)
                if index == -1:
                    break
                if tag == "[if":
                    end_index = text.find("]", index)
                    if end_index != -1:
                        self.setFormat(index, end_index - index + 1, self.conditional_format)
                        index = end_index + 1
                    else:
                        self.setFormat(index, len(tag), self.conditional_format)
                        index += len(tag)
                else:
                    self.setFormat(index, len(tag), self.conditional_format)
                    index += len(tag)
