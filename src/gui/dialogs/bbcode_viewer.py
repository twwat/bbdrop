#!/usr/bin/env python3
"""
BBCode Viewer Dialog for imx.to gallery uploader
Dialog for viewing and editing BBCode text files
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QDialogButtonBox, QMessageBox, QApplication, QStyle
)
from PyQt6.QtCore import QTimer, QSize


class BBCodeViewerDialog(QDialog):
    """Dialog for viewing and editing BBCode text files"""
    
    def __init__(self, folder_path, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.folder_name = os.path.basename(folder_path)
        self.folder_files = []

        # Import here to avoid circular imports
        from src.utils.paths import get_central_storage_path
        self.central_path: str = get_central_storage_path()  # Type annotation ensures non-None
        
        self.setWindowTitle(f"BBCode Files - {self.folder_name}")
        self.setModal(True)
        self.resize(800, 600)
        self._center_on_parent()

        # Setup UI
        layout = QVBoxLayout(self)
        
        # Info label
        self.info_label = QLabel()
        layout.addWidget(self.info_label)
        
        # Text editor
        self.text_edit = QPlainTextEdit()
        self.text_edit.setProperty("class", "console")
        layout.addWidget(self.text_edit)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        self.copy_btn.setIconSize(QSize(16, 16))
        if not self.copy_btn.text().startswith(" "):
            self.copy_btn.setText(" " + self.copy_btn.text())
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        button_layout.addWidget(self.copy_btn)
        
        button_layout.addStretch()
        
        # Standard dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.save_files)
        self.button_box.rejected.connect(self.reject)
        button_layout.addWidget(self.button_box)
        
        layout.addLayout(button_layout)
        
        # Load content
        self.load_content()
    
    def _resolve_gallery_identity(self):
        """Return (gallery_name, gallery_id) for this folder, sourced from the
        in-memory queue item when available, falling back to a DB lookup. Both
        are used to construct the canonical artifact filenames."""
        gallery_id = ""
        gallery_name = ""
        widget = self.parent()
        while widget:
            if hasattr(widget, 'queue_manager'):
                item = widget.queue_manager.get_item(self.folder_path)
                if item:
                    gallery_id = item.gallery_id or ""
                    gallery_name = item.name or ""
                break
            widget = widget.parent()
        if not gallery_id:
            try:
                from src.storage.database import QueueStore
                gallery_id = QueueStore().get_gallery_id(self.folder_path)
            except Exception:
                gallery_id = ""
        if not gallery_name:
            gallery_name = os.path.basename(self.folder_path)
        return gallery_name, gallery_id

    def get_file_paths(self):
        """Return the canonical artifact paths used by save_files()."""
        from src.storage.gallery_management import build_gallery_filenames
        gallery_name, gallery_id = self._resolve_gallery_identity()
        if gallery_id:
            _, _, bbcode_filename = build_gallery_filenames(gallery_name, gallery_id)
        else:
            bbcode_filename = f"{gallery_name}_bbcode.txt"
        base_dir = (
            self.folder_path if os.path.isdir(self.folder_path)
            else os.path.dirname(self.folder_path)
        )
        uploaded_dir = os.path.join(base_dir, ".uploaded")
        return {
            'central_bbcode': os.path.join(self.central_path, bbcode_filename),
            'folder_bbcode': os.path.join(uploaded_dir, bbcode_filename),
        }

    def load_content(self):
        """Load BBCode content via the unified DB-first resolver."""
        from src.utils.artifact_finder import resolve_gallery_bbcode
        gallery_name, gallery_id = self._resolve_gallery_identity()
        content, source = resolve_gallery_bbcode(
            gallery_path=self.folder_path,
            gallery_name=gallery_name,
            gallery_id=gallery_id,
        )

        if content:
            self.info_label.setText(f"Loaded from: {source or 'database'}")
            self.text_edit.setPlainText(content)
        else:
            self.info_label.setText("No BBCode files found for this gallery")
            self.text_edit.setPlainText("No BBCode content available")
            self.text_edit.setReadOnly(True)
            self.button_box.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
    
    def copy_to_clipboard(self):
        """Copy content to clipboard"""
        content = self.text_edit.toPlainText()
        clipboard = QApplication.clipboard()
        clipboard.setText(content)
        
        # Show brief confirmation
        self.copy_btn.setText("Copied!")
        QTimer.singleShot(1000, lambda: self.copy_btn.setText("Copy to Clipboard"))
    
    def save_files(self):
        """Save content to the database and to both .txt locations on disk."""
        content = self.text_edit.toPlainText()
        file_paths = self.get_file_paths()

        try:
            # Persist to database (primary source of truth).
            try:
                from src.storage.database import QueueStore
                _, gallery_id = self._resolve_gallery_identity()
                QueueStore().set_gallery_bbcode(
                    self.folder_path, content,
                    gallery_id=gallery_id or None,
                )
            except Exception as e:
                # Disk write below still succeeds; surface the warning but
                # don't block the save.
                from src.utils.logger import log
                log(f"BBCode viewer: DB write failed for {self.folder_path}: {e}",
                    level="warning", category="database")

            # Mirror to disk (.uploaded + central) under canonical naming.
            os.makedirs(os.path.dirname(file_paths['folder_bbcode']), exist_ok=True)
            with open(file_paths['central_bbcode'], 'w', encoding='utf-8') as f:
                f.write(content)
            with open(file_paths['folder_bbcode'], 'w', encoding='utf-8') as f:
                f.write(content)

            # Notify forum-posting hub so tracked forum_posts can stale-flag.
            db_id = self._find_gallery_db_id()
            if db_id:
                try:
                    from src.utils.forum_signals import emit_manual_rerender
                    emit_manual_rerender(int(db_id))
                except Exception:
                    pass

            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving files: {str(e)}")

    def _find_gallery_db_id(self):
        """Walk parents to find queue_manager, then return this folder's db_id."""
        widget = self.parent()
        while widget:
            if hasattr(widget, 'queue_manager'):
                item = widget.queue_manager.get_item(self.folder_path)
                return getattr(item, 'db_id', None) if item else None
            widget = widget.parent()
        return None
    def _center_on_parent(self):
        """Center dialog on parent window or screen"""
        if self.parent():
            # Center on parent window
            parent_geo = self.parent().geometry()
            dialog_geo = self.frameGeometry()
            x = parent_geo.x() + (parent_geo.width() - dialog_geo.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - dialog_geo.height()) // 2
            self.move(x, y)
        else:
            # Center on screen if no parent
            screen = QApplication.primaryScreen()
            if screen:
                screen_geo = screen.geometry()
                dialog_geo = self.frameGeometry()
                x = (screen_geo.width() - dialog_geo.width()) // 2
                y = (screen_geo.height() - dialog_geo.height()) // 2
                self.move(x, y)
