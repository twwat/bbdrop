"""
Gallery File Manager Dialog
Allows users to add/remove files from galleries and view file details
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Set

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QMessageBox, QFileDialog, QCheckBox,
    QGroupBox, QSplitter, QTextEdit, QTextBrowser, QProgressDialog, QDialogButtonBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QTimer, QUrl
from PyQt6.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent, QImage
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from src.core.constants import IMAGE_EXTENSIONS
from src.utils.logger import log


class FileScanner(QThread):
    """Background thread for scanning files"""
    progress = pyqtSignal(int, int)  # current, total
    file_scanned = pyqtSignal(str, bool, str)  # filename, is_valid, error_msg
    finished = pyqtSignal()
    
    def __init__(self, folder_path: str, files: List[str]):
        super().__init__()
        self.folder_path = folder_path
        self.files = files
        self._stop = False
    
    def run(self):
        """Scan files for validity using PIL verification"""
        from PIL import Image

        total = len(self.files)
        for i, filename in enumerate(self.files):
            if self._stop:
                break

            filepath = os.path.join(self.folder_path, filename)
            is_valid = True
            error_msg = ""

            try:
                # Check if file exists
                if not os.path.exists(filepath):
                    is_valid = False
                    error_msg = "File not found"
                # Check if it's an image extension
                elif not filename.lower().endswith(IMAGE_EXTENSIONS):
                    is_valid = False
                    error_msg = "Not an image file"
                else:
                    # Validate image format is recognized by PIL
                    try:
                        with Image.open(filepath) as img:
                            _ = img.format  # Ensure format is identified
                    except Exception as pil_error:
                        is_valid = False
                        error_msg = f"Invalid or corrupt image: {str(pil_error)}"
            except Exception as e:
                is_valid = False
                error_msg = str(e)

            self.file_scanned.emit(filename, is_valid, error_msg)
            self.progress.emit(i + 1, total)

        self.finished.emit()
    
    def stop(self):
        self._stop = True


class GalleryFileManagerDialog(QDialog):
    """Dialog for managing files in a gallery"""

    def __init__(self, gallery_path: str, queue_manager, parent=None):
        super().__init__(parent)
        self.gallery_path = gallery_path
        self.queue_manager = queue_manager
        self.gallery_item = queue_manager.get_item(gallery_path)
        self.modified: bool = False
        self.scanner: Optional[FileScanner] = None
        self._scan_progress_dialog: Optional[QProgressDialog] = None

        # Track original and current files
        self.original_files: Set[str] = set()
        self.removed_files: Set[str] = set()
        self.added_files: Set[str] = set()
        self.file_status: dict[str, tuple[bool, str]] = {}  # filename -> (is_valid, error_msg)

        # Artifact data for completed galleries
        self.artifact_data: Optional[dict] = None
        self.is_completed: bool = False

        self.setup_ui()
        self.load_gallery_files()
    
    def setup_ui(self):
        """Setup the dialog UI"""
        self.setWindowTitle(f"Manage Files - {os.path.basename(self.gallery_path)}")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout()
        
        # Gallery info - compact header
        info_group = QGroupBox("Gallery Information")
        info_group.setMaximumHeight(100)
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(5, 5, 5, 5)
        
        self.info_label = QLabel()
        self.update_info_label()
        info_layout.addWidget(self.info_label)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Main content - splitter with file list and details
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - file list
        left_widget = QGroupBox("Files")
        left_layout = QVBoxLayout()

        # File tree with columns
        self.file_list = QTreeWidget()
        self.file_list.setHeaderLabels(["Name", "Dimensions", "Size", "Status"])
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setRootIsDecorated(False)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.file_list.setAcceptDrops(True)
        self.file_list.dragEnterEvent = self.dragEnterEvent
        self.file_list.dragMoveEvent = self.dragMoveEvent
        self.file_list.dropEvent = self.dropEvent
        # Column sizing
        header = self.file_list.header()
        if header:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        left_layout.addWidget(self.file_list)
        
        # File actions
        button_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("Add Files...")
        self.add_btn.clicked.connect(self.add_files)
        button_layout.addWidget(self.add_btn)
        
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.remove_btn.setEnabled(False)
        button_layout.addWidget(self.remove_btn)
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)
        
        self.select_invalid_btn = QPushButton("Select Invalid")
        self.select_invalid_btn.clicked.connect(self.select_invalid)
        self.select_invalid_btn.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.select_invalid_btn)
        
        left_layout.addLayout(button_layout)
        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)
        
        # Right side - details
        right_widget = QGroupBox("Details")
        right_layout = QVBoxLayout()

        # Text details
        self.details_text = QTextBrowser()
        self.details_text.setOpenExternalLinks(True)
        right_layout.addWidget(self.details_text)
        
        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)
        
        splitter.setSizes([500, 300])
        layout.addWidget(splitter)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size in binary units (KiB/MiB/GiB)."""
        if size_bytes <= 0:
            return ""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KiB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MiB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GiB"

    def _get_file_dimensions(self, filename: str):
        """Get (width, height) for a file from scan data, or None."""
        if self.gallery_item:
            dims = getattr(self.gallery_item, 'file_dimensions', None)
            if isinstance(dims, dict) and filename in dims:
                d = dims[filename]
                if isinstance(d, (list, tuple)) and len(d) >= 2:
                    return int(d[0]), int(d[1])
        return None

    def _get_file_size(self, filename: str) -> int:
        """Get file size in bytes from disk."""
        filepath = os.path.join(self.gallery_path, filename)
        try:
            return os.path.getsize(filepath) if os.path.exists(filepath) else 0
        except OSError:
            return 0

    def _get_uploaded_image_data(self, filename: str) -> dict | None:
        """Get upload response data for a file from uploaded_images_data."""
        if not self.gallery_item:
            return None
        uploaded_data = getattr(self.gallery_item, 'uploaded_images_data', None)
        if not uploaded_data or not isinstance(uploaded_data, list):
            return None
        for entry in uploaded_data:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                fname, data = entry[0], entry[1]
                if fname == filename and isinstance(data, dict):
                    return data
        return None

    def _get_upload_status_for_file(self, filename: str):
        """Get upload status for a file: 'uploaded', 'failed', or 'pending'.

        Returns (status_str, error_msg_or_None).
        """
        if not self.gallery_item:
            return 'pending', None

        # Check failed_files first (list of (filename, error) tuples)
        try:
            failed_files = getattr(self.gallery_item, 'failed_files', None)
            if failed_files and isinstance(failed_files, list):
                for entry in failed_files:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        fname, error = entry[0], entry[1]
                        if fname == filename:
                            return 'failed', error
        except (TypeError, ValueError):
            pass

        # Check uploaded_files set
        try:
            uploaded_files = getattr(self.gallery_item, 'uploaded_files', None)
            if uploaded_files and isinstance(uploaded_files, (set, list, frozenset)):
                if filename in uploaded_files:
                    return 'uploaded', None
        except TypeError:
            pass

        return 'pending', None

    def _has_upload_history(self):
        """Check if this gallery has any upload attempt data."""
        if not self.gallery_item:
            return False
        try:
            uploaded = getattr(self.gallery_item, 'uploaded_files', None)
            failed = getattr(self.gallery_item, 'failed_files', None)
            has_uploaded = isinstance(uploaded, (set, list, frozenset)) and bool(uploaded)
            has_failed = isinstance(failed, list) and bool(failed)
            return has_uploaded or has_failed
        except TypeError:
            return False

    def update_info_label(self):
        """Update gallery information label"""
        if self.gallery_item:
            status = self.gallery_item.status
            total = len(self.original_files) + len(self.added_files) - len(self.removed_files)
            valid = sum(1 for v, _ in self.file_status.values() if v)
            invalid = total - valid

            has_history = self._has_upload_history()

            # Use different formatting for failed/incomplete galleries with upload history
            if status in ("failed", "upload_failed", "incomplete") and has_history:
                uploaded_count = getattr(self.gallery_item, 'uploaded_images', 0) or 0
                failed_files = getattr(self.gallery_item, 'failed_files', []) or []
                failed_count = len(failed_files)
                pending_count = max(0, total - uploaded_count - failed_count)

                color = 'red' if status in ('failed', 'upload_failed') else 'orange'
                info = f"<b><span style='color: {color};'>Status: {status.upper()}</span></b> | "
                info += f"<b>Total:</b> {total}"
                if uploaded_count:
                    info += f" | <b><span style='color: green;'>Uploaded:</span></b> {uploaded_count}"
                if failed_count:
                    info += f" | <b><span style='color: red;'>Failed:</span></b> {failed_count}"
                if pending_count > 0:
                    info += f" | <b>Pending:</b> {pending_count}"
                if invalid > 0:
                    info += f" | <b><span style='color: red;'>Invalid:</span></b> {invalid}"
                if hasattr(self.gallery_item, 'error_message') and self.gallery_item.error_message:
                    info += f"<br><b>Error:</b> {self.gallery_item.error_message}"
            elif status == "failed":
                info = f"<b><span style='color: red;'>Status: FAILED</span></b> | "
                info += f"<b>Total:</b> {total} | "
                info += f"<b>Valid:</b> {valid} | "
                info += f"<b><span style='color: red;'>Invalid:</span> {invalid}</b>"
                if hasattr(self.gallery_item, 'error_message') and self.gallery_item.error_message:
                    info += f"<br><b>Error:</b> {self.gallery_item.error_message}"
            else:
                info = f"<b>Status:</b> {status} | "
                info += f"<b>Total Files:</b> {total} | "
                info += f"<b>Valid:</b> {valid} | "
                info += f"<b>Invalid:</b> {invalid}"

                if self.gallery_item.status == "completed":
                    info += f" | <b>Uploaded:</b> {self.gallery_item.uploaded_images}"

            # Add source information
            if getattr(self.gallery_item, 'is_from_archive', False) and getattr(self.gallery_item, 'source_archive_path', None):
                archive_name = os.path.basename(self.gallery_item.source_archive_path)
                info += f"<br><b>Source:</b> {archive_name} (archive)"
            else:
                info += f"<br><b>Source:</b> {self.gallery_path}"

            self.info_label.setText(info)
        else:
            self.info_label.setText("Gallery information not available")
    
    def load_gallery_files(self):
        """Load files - from artifact for completed galleries, scan folder otherwise"""
        # Check if this is a completed gallery with artifact
        if self.gallery_item and self.gallery_item.status == "completed" and hasattr(self.gallery_item, 'gallery_id') and self.gallery_item.gallery_id:
            # Try to load from artifact (folder doesn't need to exist)
            from src.utils.artifact_finder import find_gallery_json_by_id
            import json

            json_path = find_gallery_json_by_id(self.gallery_item.gallery_id, self.gallery_path)
            if json_path and os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        self.artifact_data = json.load(f)
                    self.is_completed = True
                    self.load_from_artifact()
                    return
                except Exception as e:
                    log(f"Failed to load artifact: {e}", level="error", category="ui")
                    # Fall through to folder scan

        # Fallback: scan folder for non-completed or if artifact not found
        if not os.path.exists(self.gallery_path):
            QMessageBox.warning(self, "Error", "Gallery folder does not exist")
            return

        files = []
        for f in os.listdir(self.gallery_path):
            if f.lower().endswith(IMAGE_EXTENSIONS):
                files.append(f)
                self.original_files.add(f)

        # Start scanning files
        self.scan_files(files)

    def load_from_artifact(self):
        """Load files from artifact data for completed galleries"""
        if not self.artifact_data:
            return

        # Extract images from artifact
        images = self.artifact_data.get('images', [])
        style = self.style()

        for img_data in images:
            filename = img_data.get('original_filename', '')
            if not filename:
                continue

            self.original_files.add(filename)
            # All artifact images are valid (already uploaded successfully)
            self.file_status[filename] = (True, "")

            # Build columns: Name, Dimensions, Size, Status
            size_bytes = int(img_data.get('size_bytes', 0) or 0)
            width = int(img_data.get('width', 0) or 0)
            height = int(img_data.get('height', 0) or 0)
            dim_text = f"{width} x {height}" if width and height else ""
            size_text = self._format_size(size_bytes) if size_bytes else ""

            item = QTreeWidgetItem([filename, dim_text, size_text, "Uploaded"])
            if style is not None:
                item.setIcon(0, style.standardIcon(style.StandardPixmap.SP_DialogApplyButton))
            item.setToolTip(0, "Uploaded image")
            # Right-align size column
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.file_list.addTopLevelItem(item)

        # Disable editing for completed galleries
        self.add_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.add_btn.setToolTip("Cannot modify completed galleries")
        self.remove_btn.setToolTip("Cannot modify completed galleries")

        self.update_info_label()
        self.update_button_states()

    def scan_files(self, files: List[str]):
        """Scan files for validity in background"""
        # Cleanup any existing scanner first
        self._cleanup_scanner()

        # Show progress dialog - stored as instance variable to prevent GC
        self._scan_progress_dialog = QProgressDialog("Scanning files...", "Cancel", 0, len(files), self)
        self._scan_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)

        self.scanner = FileScanner(self.gallery_path, files)
        self.scanner.progress.connect(self._on_scan_progress)
        self.scanner.file_scanned.connect(self.on_file_scanned)
        self.scanner.finished.connect(self._on_scan_finished)

        self._scan_progress_dialog.canceled.connect(self._on_scan_canceled)

        self.scanner.start()
    
    def _on_scan_progress(self, current: int, total: int) -> None:
        """Handle scan progress update safely."""
        if self._scan_progress_dialog is not None:
            try:
                self._scan_progress_dialog.setValue(current)
            except RuntimeError:
                pass  # Dialog was deleted

    def _on_scan_finished(self) -> None:
        """Handle scan completion - safely close progress dialog."""
        if self._scan_progress_dialog is not None:
            try:
                self._scan_progress_dialog.close()
            except RuntimeError:
                pass
            self._scan_progress_dialog = None

    def _cleanup_scanner(self) -> None:
        """Stop and cleanup the file scanner thread safely."""
        if self.scanner is not None:
            if self.scanner.isRunning():
                self.scanner.stop()
                self.scanner.wait(2000)
                if self.scanner.isRunning():
                    self.scanner.terminate()
            try:
                self.scanner.progress.disconnect()
                self.scanner.file_scanned.disconnect()
                self.scanner.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.scanner = None

        if self._scan_progress_dialog is not None:
            try:
                self._scan_progress_dialog.close()
            except RuntimeError:
                pass
            self._scan_progress_dialog = None

    def _on_scan_canceled(self) -> None:
        """Handle user canceling the scan."""
        if self.scanner is not None:
            self.scanner.stop()

    def on_file_scanned(self, filename: str, is_valid: bool, error_msg: str):
        """Handle file scan result"""
        self.file_status[filename] = (is_valid, error_msg)

        # Find or create tree item
        item = None
        for i in range(self.file_list.topLevelItemCount()):
            existing = self.file_list.topLevelItem(i)
            if existing and existing.data(0, Qt.ItemDataRole.UserRole) == filename:
                item = existing
                break

        # Build column data
        dims = self._get_file_dimensions(filename)
        dim_text = f"{dims[0]} x {dims[1]}" if dims else ""
        size_bytes = self._get_file_size(filename)
        size_text = self._format_size(size_bytes) if size_bytes else ""

        # Determine status
        has_history = self._has_upload_history()
        upload_status, upload_error = self._get_upload_status_for_file(filename)

        if not is_valid:
            status_text = "Invalid"
            tooltip = f"Invalid: {error_msg}"
        elif has_history and upload_status == 'failed':
            status_text = "Failed"
            tooltip = f"Upload failed: {upload_error or 'unknown error'}"
        elif has_history and upload_status == 'uploaded':
            status_text = "Uploaded"
            tooltip = "Uploaded successfully"
        elif has_history and upload_status == 'pending':
            status_text = "Pending"
            tooltip = "Pending upload"
        else:
            status_text = "Valid"
            tooltip = "Valid image file"

        display_name = f"{filename} (new)" if filename in self.added_files else filename

        if item is None:
            item = QTreeWidgetItem([display_name, dim_text, size_text, status_text])
            item.setData(0, Qt.ItemDataRole.UserRole, filename)
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.file_list.addTopLevelItem(item)
        else:
            item.setText(0, display_name)
            item.setText(1, dim_text)
            item.setText(2, size_text)
            item.setText(3, status_text)

        # Icon and colour
        style = self.style()
        if not is_valid or (has_history and upload_status == 'failed'):
            if style is not None:
                item.setIcon(0, style.standardIcon(style.StandardPixmap.SP_DialogCancelButton))
            item.setForeground(0, Qt.GlobalColor.red)
            item.setForeground(3, Qt.GlobalColor.red)
        elif has_history and upload_status == 'uploaded':
            if style is not None:
                item.setIcon(0, style.standardIcon(style.StandardPixmap.SP_DialogApplyButton))
        elif has_history and upload_status == 'pending':
            if style is not None:
                item.setIcon(0, style.standardIcon(style.StandardPixmap.SP_ArrowRight))
        else:
            if style is not None:
                item.setIcon(0, style.standardIcon(style.StandardPixmap.SP_DialogApplyButton))

        item.setToolTip(0, tooltip)
        item.setToolTip(3, tooltip)

        self.update_info_label()
        self.update_button_states()
    
    def update_button_states(self):
        """Update button states based on file status"""
        has_invalid = any(not v for v, _ in self.file_status.values())
        # Also count upload failures as selectable
        has_failures = False
        if self._has_upload_history():
            for filename in self.file_status:
                status, _ = self._get_upload_status_for_file(filename)
                if status == 'failed':
                    has_failures = True
                    break
        self.select_invalid_btn.setEnabled(has_invalid or has_failures)

    def on_selection_changed(self):
        """Handle file selection change"""
        selected = self.file_list.selectedItems()
        self.remove_btn.setEnabled(len(selected) > 0)

        # Update details
        if len(selected) == 1:
            filename = selected[0].data(0, Qt.ItemDataRole.UserRole)
            if filename is None:
                filename = selected[0].text(0).replace(" (new)", "")
            self.show_file_details(filename)
        elif len(selected) > 1:
            self.details_text.setText(f"{len(selected)} files selected")
        else:
            self.details_text.clear()
    
    def show_file_details(self, filename: str):
        """Show details for selected file - from artifact for completed galleries"""
        # Check if we have artifact data for this file
        if self.is_completed and self.artifact_data:
            # Find the image data in the artifact
            images = self.artifact_data.get('images', [])
            img_data = None
            for img in images:
                if img.get('original_filename') == filename:
                    img_data = img
                    break

            if img_data:
                # Display artifact data
                filepath = os.path.join(self.gallery_path, filename)
                details = f"<b>File:</b> {filename}<br>"
                details += f"<b>Path:</b> {filepath}<br><br>"

                # Size
                size_bytes = int(img_data.get('size_bytes', 0) or 0)
                if size_bytes:
                    details += f"<b>Size:</b> {self._format_size(size_bytes)}<br>"

                # Dimensions
                width = int(img_data.get('width', 0) or 0)
                height = int(img_data.get('height', 0) or 0)
                if width and height:
                    details += f"<b>Dimensions:</b> {width} x {height}<br>"

                # Upload URLs
                details += "<br>"
                image_url = img_data.get('image_url', '')
                thumb_url = img_data.get('thumb_url', '') or img_data.get('thumbnail_url', '')
                if image_url:
                    details += f"<b>Image URL:</b> <a href='{image_url}'>{image_url}</a><br>"
                if thumb_url:
                    details += f"<b>Thumb URL:</b> <a href='{thumb_url}'>{thumb_url}</a><br>"

                # BBCode
                bbcode = img_data.get('bbcode', '')
                if bbcode:
                    details += f"<br><b>BBCode:</b><br><code>{bbcode}</code><br>"
                    hotlink = bbcode.replace('/u/t/', '/u/i/')
                    if hotlink != bbcode:
                        details += f"<b>Hotlink:</b><br><code>{hotlink}</code><br>"

                self.details_text.setHtml(details)
                return

        # Show local file details for non-completed galleries
        filepath = os.path.join(self.gallery_path, filename)
        details = f"<b>File:</b> {filename}<br>"
        details += f"<b>Path:</b> {filepath}<br><br>"

        # Size
        size_bytes = self._get_file_size(filename)
        if size_bytes:
            details += f"<b>Size:</b> {self._format_size(size_bytes)}<br>"

        # Dimensions — from scan data or PIL fallback
        dims = self._get_file_dimensions(filename)
        if dims:
            details += f"<b>Dimensions:</b> {dims[0]} x {dims[1]}<br>"
        elif os.path.exists(filepath):
            try:
                from PIL import Image
                with Image.open(filepath) as img:
                    details += f"<b>Dimensions:</b> {img.width} x {img.height}<br>"
                    details += f"<b>Format:</b> {img.format}<br>"
            except (OSError, IOError):
                pass

        # Validation status
        if filename in self.file_status:
            is_valid, error_msg = self.file_status[filename]
            if is_valid:
                details += "<b>Status:</b> ✅ Valid image<br>"
            else:
                details += f"<b>Status:</b> ❌ {error_msg}<br>"

        # Upload status
        upload_status, upload_error = self._get_upload_status_for_file(filename)
        has_history = self._has_upload_history()

        if has_history:
            details += "<br>"
            if upload_status == 'uploaded':
                details += "<b>Upload:</b> ✅ Uploaded successfully<br>"
                img_data = self._get_uploaded_image_data(filename)
                if img_data:
                    image_url = img_data.get('image_url', '')
                    thumb_url = img_data.get('thumb_url', '')
                    bbcode = img_data.get('bbcode', '')
                    if image_url:
                        details += f"<b>Image URL:</b> <a href='{image_url}'>{image_url}</a><br>"
                    if thumb_url:
                        details += f"<b>Thumb URL:</b> <a href='{thumb_url}'>{thumb_url}</a><br>"
                    if bbcode:
                        details += f"<b>BBCode:</b><br><code>{bbcode}</code><br>"
            elif upload_status == 'failed':
                details += f"<b>Upload:</b> ❌ Failed — {upload_error or 'unknown error'}<br>"
            else:
                details += "<b>Upload:</b> ⏳ Not yet attempted<br>"

        if not os.path.exists(filepath):
            details += "<br><b>Note:</b> File not found on disk<br>"

        # Action hints
        if filename in self.added_files:
            details += "<br><i>This file was added in this session</i>"
        elif filename in self.removed_files:
            details += "<br><i>This file is marked for removal</i>"

        self.details_text.setHtml(details)

    def add_files(self):
        """Add files to the gallery"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images to Add",
            "",
            "Images (*.jpg *.jpeg *.png *.gif);;All Files (*.*)"
        )
        
        if files:
            added_count = 0
            for filepath in files:
                filename = os.path.basename(filepath)
                dest_path = os.path.join(self.gallery_path, filename)
                
                # Check if file already exists
                if os.path.exists(dest_path):
                    reply = QMessageBox.question(
                        self,
                        "File Exists",
                        f"{filename} already exists. Replace it?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        continue
                
                try:
                    # Copy file to gallery folder
                    shutil.copy2(filepath, dest_path)
                    self.added_files.add(filename)
                    if filename in self.removed_files:
                        self.removed_files.remove(filename)
                    added_count += 1
                    self.modified = True
                    
                    # Scan the new file
                    self.scan_files([filename])
                    
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to add {filename}: {e}")
            
            if added_count > 0:
                self.update_info_label()
                QMessageBox.information(self, "Success", f"Added {added_count} file(s)")
    
    def remove_selected(self):
        """Remove selected files"""
        selected = self.file_list.selectedItems()
        if not selected:
            return
        
        count = len(selected)
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove {count} file(s) from the gallery?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for item in selected:
                filename = item.data(0, Qt.ItemDataRole.UserRole)
                if filename is None:
                    filename = item.text(0).replace(" (new)", "")
                filepath = os.path.join(self.gallery_path, filename)

                try:
                    # Delete the file
                    if os.path.exists(filepath):
                        os.remove(filepath)

                    # Update tracking
                    self.removed_files.add(filename)
                    if filename in self.added_files:
                        self.added_files.remove(filename)

                    # Remove from tree
                    idx = self.file_list.indexOfTopLevelItem(item)
                    if idx >= 0:
                        self.file_list.takeTopLevelItem(idx)

                    # Remove from status tracking
                    if filename in self.file_status:
                        del self.file_status[filename]

                    self.modified = True

                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to remove {filename}: {e}")
            
            self.update_info_label()
    
    def select_all(self):
        """Select all files"""
        self.file_list.selectAll()
    
    def select_invalid(self):
        """Select invalid files and failed uploads"""
        self.file_list.clearSelection()
        for i in range(self.file_list.topLevelItemCount()):
            item = self.file_list.topLevelItem(i)
            if item is None:
                continue
            filename = item.data(0, Qt.ItemDataRole.UserRole)
            if filename is None:
                filename = item.text(0).replace(" (new)", "")
            if filename in self.file_status:
                is_valid, _ = self.file_status[filename]
                if not is_valid:
                    item.setSelected(True)
                    continue
            # Also select failed uploads
            upload_status, _ = self._get_upload_status_for_file(filename)
            if upload_status == 'failed':
                item.setSelected(True)
    
    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        """Handle drag enter"""
        if event is None:
            return
        mime_data = event.mimeData()
        if mime_data is not None and mime_data.hasUrls():
            # Check if any URLs are image files
            for url in mime_data.urls():
                path = url.toLocalFile()
                if path.lower().endswith(IMAGE_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dragMoveEvent(self, event) -> None:
        """Handle drag move"""
        if event is None:
            return
        mime_data = event.mimeData()
        if mime_data is not None and mime_data.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event: QDropEvent | None) -> None:
        """Handle drop event - add dropped files"""
        if event is None:
            return
        mime_data = event.mimeData()
        if mime_data is not None and mime_data.hasUrls():
            files: List[str] = []
            for url in mime_data.urls():
                path = url.toLocalFile()
                if os.path.isfile(path) and path.lower().endswith(IMAGE_EXTENSIONS):
                    files.append(path)

            if files:
                # Add the files
                event.acceptProposedAction()
                self.add_files_internal(files)
            else:
                event.ignore()
        else:
            event.ignore()
    
    def add_files_internal(self, files: List[str]):
        """Internal method to add files (used by drag-drop)"""
        added_count = 0
        for filepath in files:
            filename = os.path.basename(filepath)
            dest_path = os.path.join(self.gallery_path, filename)
            
            # Skip if file already exists
            if os.path.exists(dest_path) and filepath != dest_path:
                continue
            
            try:
                # Copy file to gallery folder if not already there
                if filepath != dest_path:
                    shutil.copy2(filepath, dest_path)
                
                self.added_files.add(filename)
                if filename in self.removed_files:
                    self.removed_files.remove(filename)
                added_count += 1
                self.modified = True
                
                # Scan the new file
                self.scan_files([filename])
                
            except Exception as e:
                log(f"Failed to add {filename}: {e}", level="error", category="ui")
        
        if added_count > 0:
            self.update_info_label()
    
    def accept(self):
        """Accept changes and close dialog"""
        self._cleanup_scanner()
        if self.modified:
            # Update queue manager if needed
            if self.gallery_item:
                # Trigger rescan of the gallery
                if self.gallery_item.status in ("ready", "failed", "paused", "incomplete"):
                    # Full rescan for not-yet-uploaded galleries
                    self.queue_manager.scan_folder(self.gallery_path)
                elif self.gallery_item.status == "completed":
                    # For completed galleries, just update the file count
                    new_total = len(self.original_files) + len(self.added_files) - len(self.removed_files)
                    if new_total > self.gallery_item.uploaded_images:
                        # Mark as incomplete to allow uploading new files
                        self.gallery_item.status = "incomplete"
                        self.gallery_item.total_images = new_total
                        # Progress will be adjusted when upload starts
        
        super().accept()

    def reject(self):
        """Handle dialog rejection/cancel"""
        self._cleanup_scanner()
        super().reject()

    def closeEvent(self, event):
        """Handle dialog close event"""
        self._cleanup_scanner()
        super().closeEvent(event)