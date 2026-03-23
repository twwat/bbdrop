"""File host upload controller for BBDrop GUI.

Handles all file host upload operations: triggering uploads, managing icons,
showing detail dialogs, handling missing folders, and sibling gallery detection.
"""

import os
import traceback
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QObject, Qt

from src.utils.logger import log

if TYPE_CHECKING:
    from src.gui.main_window import BBDropGUI


class FileHostController(QObject):
    """Controls file host upload operations and UI interactions."""

    def __init__(self, main_window: 'BBDropGUI'):
        super().__init__()
        self._main_window = main_window
        self._db_id_to_path = {}

    def _refresh_file_host_widgets_for_db_id(self, db_id: int):
        """Refresh file host widgets for a specific gallery ID - OPTIMIZED VERSION

        This method is called asynchronously via QTimer to avoid blocking signal emission.
        Optimized to use O(1) lookups instead of iterating all items.
        """
        try:
            from src.gui.widgets.gallery_table import GalleryTableWidget

            # 1. Entry point logging
            log(f"_refresh_file_host_widgets_for_db_id called with db_id={db_id}",
                level="debug", category="file_hosts")

            # OPTIMIZATION 1: Use cached db_id -> path mapping if available
            # This avoids iterating through all queue items
            gallery_path = self._db_id_to_path.get(db_id)

            # 2. Log cache lookup result
            log(f"db_id {db_id} in _db_id_to_path: {db_id in self._db_id_to_path}, "
                f"mapped path: {gallery_path}", level="debug", category="file_hosts")

            # If not cached, fall back to search (only on first miss)
            if not gallery_path:
                log(f"Cache miss for db_id {db_id}, searching queue items",
                    level="debug", category="file_hosts")
                for item in self._main_window.queue_manager.get_all_items():
                    if item.db_id and item.db_id == db_id:
                        gallery_path = item.path
                        # Cache for future lookups
                        self._db_id_to_path[db_id] = gallery_path
                        log(f"Found and cached: db_id {db_id} -> path {gallery_path}",
                            level="debug", category="file_hosts")
                        break

            if not gallery_path:
                log(f"No path found for db_id {db_id}, exiting",
                    level="debug", category="file_hosts")
                return

            # OPTIMIZATION 2: O(1) row lookup via path_to_row dict
            row = self._main_window.path_to_row.get(gallery_path)

            # 3. Log row lookup result
            log(f"path '{gallery_path}' in path_to_row: {gallery_path in self._main_window.path_to_row}, "
                f"mapped row: {row}", level="debug", category="file_hosts")

            if row is None:
                log(f"No row found for path '{gallery_path}', exiting",
                    level="debug", category="file_hosts")
                return

            # Get table item for delegate-based rendering
            hosts_item = self._main_window.gallery_table.table.item(row, GalleryTableWidget.COL_HOSTS_STATUS)

            # 4. Log item lookup result
            log(f"table.item(row={row}, COL_HOSTS_STATUS) returned: {hosts_item}",
                level="debug", category="file_hosts")

            if hosts_item is None:
                log(f"File host status item not found at row {row} for db_id {db_id}", level="debug", category="file_hosts")
                return  # Item not present, skip DB query

            # Fetch file host uploads from database
            host_uploads = {}
            try:
                uploads_list = self._main_window.queue_manager.store.get_file_host_uploads(gallery_path)
                # Convert list to dict format for delegate
                host_uploads = {upload['host_name']: upload for upload in uploads_list}

                # 5. Log uploads fetched from database
                log(f"Fetched {len(uploads_list)} file host uploads from database for path '{gallery_path}': "
                    f"hosts={list(host_uploads.keys())}", level="debug", category="file_hosts")

            except Exception as e:
                log(f"Failed to load file host uploads: {e}", level="warning", category="file_hosts")
                return

            # Update table item data for delegate rendering
            hosts_item.setData(Qt.ItemDataRole.UserRole + 1, host_uploads)

            # Force repaint of the cell
            table = self._main_window.gallery_table.table
            table.viewport().update(table.visualItemRect(hosts_item))

            # Update cache with dict format for consistency
            if hasattr(self._main_window, '_file_host_uploads_cache') and gallery_path:
                self._main_window._file_host_uploads_cache[gallery_path] = uploads_list

            # 6. Confirm update completed
            log(f"Updated table item data at row {row} with {len(host_uploads)} hosts",
                level="debug", category="file_hosts")

        except Exception as e:
            # 7. Log any exceptions
            log(f"Exception in _refresh_file_host_widgets_for_db_id(db_id={db_id}): {e}",
                level="debug", category="file_hosts")
            log(f"Error refreshing file host widgets: {e}", level="error", category="file_hosts")
            traceback.print_exc()

    def start_upload_for_item(self, path: str):
        """Start upload for a specific item"""
        try:
            item = self._main_window.queue_manager.get_item(path)
            if not item:
                return False

            if item.status in ("ready", "paused", "incomplete", "upload_failed"):
                success = self._main_window.queue_manager.start_item(path)
                if success:
                    self._main_window._update_specific_gallery_display(path)  # Update only this item
                    return True
                else:
                    log(f"Failed to start upload for: {path}", level="warning", category="queue")
                    return False
            else:
                log(f"Cannot start upload for item with status: {item.status}", level="debug", category="queue")
                return False
        except Exception as e:
            log(f"Exception starting upload for {path}: {e}", level="error", category="queue")
            return False

    def _on_file_host_icon_clicked(self, gallery_path: str, host_name: str):
        """Handle file host icon click — show details dialog with actions."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
        from PyQt6.QtCore import Qt
        from src.core.host_registry import get_display_name
        from datetime import datetime

        log(f"File host icon clicked: {host_name} for {os.path.basename(gallery_path)}", level="debug", category="file_hosts")

        try:
            uploads = self._main_window.queue_manager.store.get_file_host_uploads(gallery_path)
            upload = next((u for u in uploads if u['host_name'] == host_name), None)
        except Exception as e:
            log(f"Error loading upload data: {e}", level="error", category="file_hosts")
            return

        display_name = get_display_name(host_name)

        # If not yet uploaded, queue upload directly
        if not upload or upload['status'] not in ('completed', 'failed'):
            if not upload:
                self._queue_file_host_upload(gallery_path, host_name, display_name)
            return

        # Build details dialog
        dlg = QDialog(self._main_window)
        dlg.setWindowTitle(f"{display_name} — {os.path.basename(gallery_path)}")
        dlg.setMinimumWidth(550)
        layout = QVBoxLayout(dlg)

        # Status info
        status = upload.get('status', 'unknown')
        download_url = upload.get('download_url', '')

        # Upload date
        finished_ts = upload.get('finished_ts')
        if finished_ts:
            try:
                upload_date = datetime.fromtimestamp(int(finished_ts)).strftime('%Y-%m-%d %H:%M')
            except (ValueError, OSError):
                upload_date = 'Unknown'
        else:
            upload_date = 'Unknown'

        # Scan status
        scan_data = getattr(self._main_window, '_scan_status_cache', {}).get((gallery_path, host_name))
        if scan_data:
            checked_ts = scan_data.get('checked_ts')
            try:
                checked_date = datetime.fromtimestamp(int(checked_ts)).strftime('%Y-%m-%d %H:%M')
            except (ValueError, OSError):
                checked_date = 'Unknown'
            online_status = scan_data.get('status', 'unknown').title()
        else:
            checked_date = 'Never'
            online_status = 'Unknown'

        # Info labels
        info_text = f"<b>Status:</b> {status.title()}<br>"
        info_text += f"<b>Uploaded:</b> {upload_date}<br>"
        info_text += f"<b>Last checked:</b> {checked_date}<br>"
        info_text += f"<b>Online status:</b> {online_status}"
        info_label = QLabel(info_text)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_label)

        # Download link (selectable)
        if download_url:
            link_label = QLabel(download_url)
            link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            link_label.setWordWrap(False)
            layout.addWidget(link_label)

        # Error message for failed uploads
        if status == 'failed':
            error_msg = upload.get('error_message', 'Unknown error')
            error_label = QLabel(f"<b>Error:</b> {error_msg}")
            error_label.setTextFormat(Qt.TextFormat.RichText)
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if download_url:
            copy_btn = QPushButton("Copy Link")
            copy_btn.clicked.connect(lambda: (
                QApplication.clipboard().setText(download_url),
                log(f"Copied {host_name} link to clipboard", level="info", category="file_hosts"),
                dlg.accept()
            ))
            btn_layout.addWidget(copy_btn)

        check_btn = QPushButton("Check Status")
        check_btn.clicked.connect(lambda: self._live_check_file_host(
            gallery_path, host_name, display_name, dlg))
        btn_layout.addWidget(check_btn)

        reupload_btn = QPushButton("Reupload")
        reupload_btn.clicked.connect(lambda: (
            self._queue_file_host_upload(gallery_path, host_name, display_name),
            dlg.accept()
        ))
        btn_layout.addWidget(reupload_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        dlg.exec()

    def _queue_file_host_upload(self, gallery_path: str, host_name: str, display_name: str):
        """Queue a file host upload for a gallery."""
        from PyQt6.QtWidgets import QMessageBox

        if not os.path.isdir(gallery_path):
            new_path = self._handle_missing_gallery_folder(gallery_path, host_name)
            if new_path:
                gallery_path = new_path
            else:
                return

        from src.core.file_host_config import get_config_manager
        config_manager = get_config_manager()
        if not config_manager.get_host(host_name):
            QMessageBox.warning(self._main_window, "Error", f"Host configuration not found: {host_name}")
            return

        log(f"Queueing manual upload to {host_name} for {os.path.basename(gallery_path)}", level="info", category="file_hosts")
        upload_id = self._main_window.queue_manager.store.add_file_host_upload(
            gallery_path=gallery_path,
            host_name=host_name,
            status='pending'
        )
        log(f"Queued manual upload (upload_id={upload_id}) for {os.path.basename(gallery_path)} to {host_name}", level="info", category="file_hosts")
        self._main_window._update_specific_gallery_display(gallery_path)
        QMessageBox.information(self._main_window, "Upload Queued",
            f"Gallery queued for upload to {display_name}.\nThe upload will begin shortly.")

    def _live_check_file_host(self, gallery_path: str, host_name: str, display_name: str, parent_dialog=None):
        """Perform a live online status check for a single file host upload."""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(parent_dialog or self._main_window, "Check Status",
            f"Live status check for {display_name} is not yet implemented.")

    def _handle_missing_gallery_folder(self, gallery_path: str, host_name: str) -> Optional[str]:
        """Handle missing gallery folder - offer to relocate or remove.

        Args:
            gallery_path: Path to the missing gallery
            host_name: Name of the file host (for context in messages)

        Returns:
            New path if user relocated the gallery, None if cancelled/removed
        """
        from PyQt6.QtWidgets import QMessageBox, QFileDialog

        gallery_name = os.path.basename(gallery_path)
        old_parent = os.path.dirname(gallery_path)

        # Create dialog with options
        msg = QMessageBox(self._main_window)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Gallery Folder Not Found")
        msg.setText(f"The gallery folder no longer exists:\n{gallery_path}")
        msg.setInformativeText("Would you like to locate it?")

        browse_btn = msg.addButton("Browse...", QMessageBox.ButtonRole.ActionRole)
        remove_btn = msg.addButton("Remove from Queue", QMessageBox.ButtonRole.DestructiveRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)

        msg.exec()
        clicked = msg.clickedButton()

        if clicked == browse_btn:
            # Let user browse for new location
            new_path = QFileDialog.getExistingDirectory(
                self._main_window,
                f"Locate Gallery: {gallery_name}",
                os.path.dirname(old_parent) if os.path.exists(os.path.dirname(old_parent)) else "",
                QFileDialog.Option.ShowDirsOnly
            )

            if new_path and os.path.isdir(new_path):
                # Update database
                success = self._main_window.queue_manager.store.update_gallery_path(gallery_path, new_path)

                if success:
                    log(f"User relocated gallery: {gallery_path} -> {new_path}", level="info", category="file_hosts")

                    # Refresh the table to show updated path
                    self._main_window._refresh_gallery_table()

                    # Check for sibling galleries that might also need updating
                    self._check_sibling_galleries(old_parent, os.path.dirname(new_path), gallery_path)

                    return new_path
                else:
                    QMessageBox.warning(self._main_window, "Error", "Failed to update gallery path in database.")
                    return None

        elif clicked == remove_btn:
            # Remove gallery from queue
            try:
                self._main_window.queue_manager.remove_items([gallery_path])
                self._main_window._refresh_gallery_table()
                log(f"User removed missing gallery from queue: {gallery_path}", level="info", category="file_hosts")
            except Exception as e:
                log(f"Error removing gallery: {e}", level="error", category="file_hosts")

        return None

    def _check_sibling_galleries(self, old_parent: str, new_parent: str, already_relocated: str):
        """Check if other galleries from the same parent folder need updating.

        Args:
            old_parent: Original parent folder
            new_parent: New parent folder where gallery was relocated
            already_relocated: Path that was just relocated (skip this one)
        """
        from PyQt6.QtWidgets import QMessageBox, QCheckBox, QVBoxLayout, QDialog, QDialogButtonBox, QLabel

        # Get all galleries that were in the same parent folder
        try:
            siblings = self._main_window.queue_manager.store.get_galleries_by_parent_folder(old_parent)
        except Exception as e:
            log(f"Error checking sibling galleries: {e}", level="error", category="ui")
            return

        # Filter to only those that are missing but exist in new location
        relocatable = []
        for gal in siblings:
            if gal['path'] == already_relocated:
                continue
            if os.path.isdir(gal['path']):
                continue  # Still exists, no need to relocate

            # Check if it exists under the new parent
            gallery_name = os.path.basename(gal['path'])
            potential_new_path = os.path.join(new_parent, gallery_name)
            if os.path.isdir(potential_new_path):
                relocatable.append({
                    'old_path': gal['path'],
                    'new_path': potential_new_path,
                    'name': gal['name'] or gallery_name
                })

        if not relocatable:
            return

        # Show dialog to update siblings
        dialog = QDialog(self._main_window)
        dialog.setWindowTitle("Update Related Galleries")
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel(
            f"Found {len(relocatable)} other galleries from the same folder\n"
            f"that also exist in the new location.\n\n"
            f"Select which ones to update:"
        ))

        checkboxes = []
        for item in relocatable:
            cb = QCheckBox(f"{item['name']}")
            cb.setChecked(True)
            cb.setProperty("paths", (item['old_path'], item['new_path']))
            checkboxes.append(cb)
            layout.addWidget(cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = 0
            for cb in checkboxes:
                if cb.isChecked():
                    old_path, new_path = cb.property("paths")
                    if self._main_window.queue_manager.store.update_gallery_path(old_path, new_path):
                        updated += 1

            if updated > 0:
                log(f"Batch relocated {updated} sibling galleries", level="info", category="file_hosts")
                self._main_window._refresh_gallery_table()

    def _on_file_hosts_manage_clicked(self, gallery_path: str):
        """Handle 'Manage' button click - show File Host Details Dialog"""
        log(f"File hosts manage clicked for {os.path.basename(gallery_path)}", level="debug", category="file_hosts")

        # TODO: Phase 6 - Implement File Host Details Dialog
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self._main_window,
            "File Hosts",
            f"File Host Details Dialog will be implemented in Phase 6.\n\nGallery: {os.path.basename(gallery_path)}"
        )

    def _on_file_hosts_enabled_changed(self, _enabled_worker_ids: list):
        """Refresh all file host widgets when enabled hosts change."""
        from src.gui.widgets.gallery_table import GalleryTableWidget

        # Skip during startup - icons are created via normal widget creation
        if not self._main_window._file_host_startup_complete:
            return

        # Remove disabled workers from status widget
        self._main_window.worker_signal_handler._on_enabled_workers_changed(_enabled_worker_ids)

        # Get all gallery paths
        items = self._main_window.queue_manager.get_all_items()

        # Batch query for all file host uploads
        file_host_uploads_map = {}
        for item in items:
            uploads = self._main_window.queue_manager.store.get_file_host_uploads(item.path)
            file_host_uploads_map[item.path] = {u['host_name']: u for u in uploads}

        # Update all file host status table items for delegate rendering
        table = self._main_window.gallery_table.table
        for row in range(self._main_window.gallery_table.rowCount()):
            path = self._main_window.row_to_path.get(row)
            if path:
                hosts_item = table.item(row, GalleryTableWidget.COL_HOSTS_STATUS)
                if hosts_item:
                    host_uploads = file_host_uploads_map.get(path, {})
                    hosts_item.setData(Qt.ItemDataRole.UserRole + 1, host_uploads)
        # Force full table repaint
        table.viewport().update()

    def _on_file_host_icon_right_clicked(self, gallery_path: str, host_name: str, global_pos):
        """Show context menu on right-click of file host icon."""
        from PyQt6.QtWidgets import QMenu, QApplication
        from src.core.host_registry import get_display_name

        display_name = get_display_name(host_name)

        try:
            uploads = self._main_window.queue_manager.store.get_file_host_uploads(gallery_path)
            upload = next((u for u in uploads if u['host_name'] == host_name), None)
        except Exception:
            upload = None

        menu = QMenu(self._main_window)

        if upload and upload.get('download_url'):
            copy_action = menu.addAction("Copy Link")
            copy_action.triggered.connect(lambda: (
                QApplication.clipboard().setText(upload['download_url']),
                log(f"Copied {host_name} link to clipboard", level="info", category="file_hosts")
            ))

        check_action = menu.addAction("Check Online Status")
        check_action.triggered.connect(
            lambda: self._live_check_file_host(gallery_path, host_name, display_name))
        if not upload or upload.get('status') != 'completed':
            check_action.setEnabled(False)

        reupload_action = menu.addAction(f"Reupload to {display_name}")
        reupload_action.triggered.connect(
            lambda: self._queue_file_host_upload(gallery_path, host_name, display_name))

        menu.exec(global_pos)

    def _on_file_host_icon_double_clicked(self, gallery_path: str, host_name: str):
        """Double-click on file host icon triggers reupload directly."""
        from src.core.host_registry import get_display_name
        display_name = get_display_name(host_name)
        self._queue_file_host_upload(gallery_path, host_name, display_name)

    def _handle_file_host_click(self, path: str, host_name: str) -> None:
        """Handle file host icon clicks from delegate.

        Args:
            path: Gallery path
            host_name: Name of the clicked host
        """
        # Delegate to existing handler
        self._on_file_host_icon_clicked(path, host_name)

    def _handle_action_button(self, path: str, action: str) -> None:
        """Handle action button clicks from delegate.

        Args:
            path: Gallery path
            action: Action to perform (start, stop, cancel, view, view_error)
        """
        if action == "start":
            self._main_window.start_single_item(path)
        elif action == "stop":
            self._main_window.gallery_queue_controller.stop_gallery(path)
        elif action == "cancel":
            self._main_window.gallery_queue_controller.cancel_gallery(path)
        elif action == "view":
            self._main_window.view_bbcode_files(path)
        elif action == "view_error":
            self._main_window._show_error_details(path)
