#!/usr/bin/env python3
"""
Update Dialog for BBDrop

Modal dialog showing available update information with download option.
"""

import re
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTextBrowser, QPushButton, QCheckBox, QApplication
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont


def _format_release_date(raw: str) -> str:
    """Turn GitHub's ISO timestamp (2026-11-03T12:00:00Z) into 'November 3, 2026'."""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return raw
    return f"{dt:%B} {dt.day}, {dt.year}"


# A bare URL not already inside a markdown link "(...)" or autolink "<...>".
_BARE_URL = re.compile(r'(?<![(<])\bhttps?://[^\s<>()]*[^\s<>().,;:!?\'"]')


def _link_bare_urls(markdown: str) -> str:
    """Wrap bare URLs in <...> so Qt links the whole URL.

    Qt's own bare-URL detection stops at '...', which cuts GitHub compare
    links (v0.9.9...v0.9.10) short.
    """
    return _BARE_URL.sub(lambda m: f"<{m.group(0)}>", markdown)


class UpdateDialog(QDialog):
    """Dialog showing available update information with download option.

    Displays version comparison, release date, release notes, and provides
    options to download or skip the update.

    Args:
        parent: Parent widget.
        current_version: Currently installed version string.
        new_version: New available version string.
        release_url: URL to the release page for download.
        release_notes: Markdown/text content of release notes.
        release_date: Date string when the release was published.
    """

    def __init__(
        self,
        parent,
        current_version: str,
        new_version: str,
        release_url: str,
        release_notes: str,
        release_date: str
    ):
        super().__init__(parent)
        self._release_url = release_url
        self._setup_dialog()
        self._create_ui(current_version, new_version, release_date, release_notes)
        self._center_on_parent()

    def _setup_dialog(self):
        """Configure dialog window properties."""
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setMinimumSize(560, 450)
        self.resize(680, 620)

    def _create_ui(
        self,
        current_version: str,
        new_version: str,
        release_date: str,
        release_notes: str
    ):
        """Create and arrange UI components.

        Args:
            current_version: Currently installed version.
            new_version: New available version.
            release_date: Release date string.
            release_notes: Release notes content.
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header label
        header_label = QLabel("A new version is available!")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(14)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        # Version info
        version_label = QLabel(f"Current: {current_version}  ->  New: {new_version}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_font = QFont()
        version_font.setPointSize(11)
        version_label.setFont(version_font)
        layout.addWidget(version_label)

        # Release date
        date_label = QLabel(f"Released: {_format_release_date(release_date)}")
        date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        date_label.setStyleSheet("color: gray;")
        layout.addWidget(date_label)

        # Spacing before release notes
        layout.addSpacing(10)

        # Release notes label
        notes_header = QLabel("Release Notes:")
        notes_header.setStyleSheet("font-weight: bold;")
        layout.addWidget(notes_header)

        # Release notes content: GitHub release bodies are markdown, so render
        # them (headings, bold, lists, links) and open links in the browser.
        self._notes_viewer = QTextBrowser()
        self._notes_viewer.setOpenExternalLinks(True)
        self._notes_viewer.setMarkdown(_link_bare_urls(release_notes or ""))
        self._notes_viewer.setMinimumHeight(200)
        layout.addWidget(self._notes_viewer, 1)

        # Skip checkbox
        self._skip_checkbox = QCheckBox("Don't remind me about this version")
        layout.addWidget(self._skip_checkbox)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        remind_later_btn = QPushButton("Remind Me Later")
        remind_later_btn.clicked.connect(self._on_remind_later_clicked)
        button_layout.addWidget(remind_later_btn)

        download_btn = QPushButton("Download Update")
        download_btn.setDefault(True)
        download_btn.clicked.connect(self._on_download_clicked)
        button_layout.addWidget(download_btn)

        layout.addLayout(button_layout)

    def _on_download_clicked(self):
        """Open release URL in browser and close dialog."""
        QDesktopServices.openUrl(QUrl(self._release_url))
        self.accept()

    def _on_remind_later_clicked(self):
        """Close dialog without action."""
        self.reject()

    @property
    def skip_version(self) -> bool:
        """Return True if user checked 'Don't remind me about this version'.

        Returns:
            True if the skip checkbox is checked, False otherwise.
        """
        return self._skip_checkbox.isChecked()

    def _center_on_parent(self):
        """Center dialog on parent window or screen."""
        if self.parent():
            parent_geo = self.parent().geometry()
            self.move(
                parent_geo.x() + (parent_geo.width() - self.width()) // 2,
                parent_geo.y() + (parent_geo.height() - self.height()) // 2
            )
        else:
            screen_geo = QApplication.primaryScreen().availableGeometry()
            self.move(
                (screen_geo.width() - self.width()) // 2,
                (screen_geo.height() - self.height()) // 2
            )
