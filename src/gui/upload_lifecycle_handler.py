"""Upload lifecycle signal handlers for BBDrop GUI.

This module handles upload lifecycle events (gallery started, progress updated,
gallery completed, gallery failed, etc.) extracted from main_window.py to
improve maintainability and separation of concerns.

Handles:
    - Gallery start/completion/failure signal processing
    - Progress update batching and display
    - File host trigger automation on lifecycle events
    - Post-completion stats and artifact handling
    - Gallery rename tracking
    - External field updates from hooks
"""

import os
import time
import traceback
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, QMutexLocker, Qt, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from src.utils.logger import log
from src.gui.widgets.custom_widgets import TableProgressWidget, ActionButtonWidget
from src.gui.widgets.gallery_table import GalleryTableWidget

if TYPE_CHECKING:
    from src.gui.main_window import BBDropGUI


class UploadLifecycleHandler(QObject):
    """Handles upload lifecycle signal events for the main window.

    Delegates from BBDropGUI to keep the main window class focused on
    layout and coordination. All methods access main window state via
    self._main_window.
    """

    def __init__(self, main_window: 'BBDropGUI'):
        super().__init__()
        self._main_window = main_window

    def on_gallery_started(self, path: str, total_images: int):
        """Handle gallery start"""
        mw = self._main_window
        with QMutexLocker(mw.queue_manager.mutex):
            if path in mw.queue_manager.items:
                item = mw.queue_manager.items[path]
                item.total_images = total_images
                item.uploaded_images = 0

        # Check for file host auto-upload triggers (on_started)
        try:
            from src.core.file_host_config import get_config_manager
            config_manager = get_config_manager()
            triggered_hosts = config_manager.get_hosts_by_trigger('started')

            if triggered_hosts:
                log(f"Gallery started trigger: Found {len(triggered_hosts)} enabled hosts with 'On Started' trigger",
                    level="info", category="file_hosts")

                for host_id, host_config in triggered_hosts.items():
                    # Queue upload to this file host (use host_id, not display name)
                    upload_id = mw.queue_manager.store.add_file_host_upload(
                        gallery_path=path,
                        host_name=host_id,  # host_id like 'filedot', not display name
                        status='pending'
                    )

                    if upload_id:
                        log(f"Queued file host upload for {path} to {host_config.name} (upload_id={upload_id})",
                            level="info", category="file_hosts")
                        mw.worker_signal_handler._update_filehost_queue_for_host(host_id)
                    else:
                        log(f"Failed to queue file host upload for {path} to {host_config.name}",
                            level="error", category="file_hosts")
        except Exception as e:
            log(f"Error checking file host triggers on gallery start: {e}", level="error", category="file_hosts")

        # Update only the specific row status instead of full table refresh
        # Use O(1) path lookup instead of O(n) row iteration
        row = mw._get_row_for_path(path)
        if row is not None:
            # Update uploaded count
            uploaded_text = f"0/{total_images}"
            uploaded_item = QTableWidgetItem(uploaded_text)
            uploaded_item.setFlags(uploaded_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            uploaded_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            mw.gallery_table.setItem(row, GalleryTableWidget.COL_UPLOADED, uploaded_item)

            # Update status cell
            current_status = item.status
            mw._set_status_cell_icon(row, current_status)
            mw._set_status_text_cell(row, current_status)

            # Update action buttons
            action_widget = mw.gallery_table.cellWidget(row, GalleryTableWidget.COL_ACTION)
            if isinstance(action_widget, ActionButtonWidget):
                action_widget.update_buttons(current_status)

        # Update button counts and progress after gallery starts
        QTimer.singleShot(0, mw.progress_tracker._update_counts_and_progress)

    def on_progress_updated(self, path: str, completed: int, total: int, progress_percent: int, current_image: str):
        """Handle progress updates from worker - NON-BLOCKING"""
        mw = self._main_window
        # Only update the data model (fast operation)
        with QMutexLocker(mw.queue_manager.mutex):
            if path in mw.queue_manager.items:
                item = mw.queue_manager.items[path]
                item.uploaded_images = completed
                item.total_images = total
                item.progress = progress_percent
                item.current_image = current_image
                # Update live transfer speed using centralized BandwidthManager
                try:
                    # Only update speed if it's currently uploading
                    if item.status == "uploading":
                        item.current_kibps = mw.worker_signal_handler.bandwidth_manager.get_imx_bandwidth()
                except Exception as e:
                    log(f"Exception in main_window: {e}", level="error", category="ui")
                    raise

        # Add to batched progress updates for non-blocking GUI updates
        mw._progress_batcher.add_update(path, completed, total, progress_percent, current_image)

    def _process_batched_progress_update(self, path: str, completed: int, total: int, progress_percent: int, current_image: str):
        """Process batched progress updates on main thread - minimal operations only"""
        mw = self._main_window
        try:
            # Get fresh data from model
            item = mw.queue_manager.get_item(path)
            if not item:
                return

            # Find row (thread-safe lookup)
            matched_row = mw._get_row_for_path(path)
            if matched_row is None or matched_row >= mw.gallery_table.rowCount():
                return

            # Update essential columns directly since table update queue may not work
            # Upload progress column (column 2)
            uploaded_text = f"{completed}/{total}" if total > 0 else "0/?"
            uploaded_item = QTableWidgetItem(uploaded_text)
            uploaded_item.setFlags(uploaded_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            uploaded_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            mw.gallery_table.setItem(matched_row, GalleryTableWidget.COL_UPLOADED, uploaded_item)

            # Progress bar (column 3)
            progress_widget = mw.gallery_table.cellWidget(matched_row, 3)
            if isinstance(progress_widget, TableProgressWidget):
                progress_widget.update_progress(progress_percent, item.status)

            # Transfer speed column (column 10) - show live speed for uploading items
            if item.status == "uploading":
                current_rate_kib = float(getattr(item, 'current_kibps', 0.0) or 0.0)
                try:
                    from src.utils.format_utils import format_binary_rate
                    if current_rate_kib > 0:
                        transfer_text = format_binary_rate(current_rate_kib, precision=2)
                    else:
                        # Show visual indicator even when speed is 0
                        transfer_text = "Uploading..."
                except Exception as e:
                    log(f"Rate formatting failed: {e}", level="warning", category="ui")
                    if current_rate_kib > 0:
                        transfer_text = mw._format_rate_consistent(current_rate_kib)
                    else:
                        transfer_text = "Uploading..."

                xfer_item = QTableWidgetItem(transfer_text)
                xfer_item.setFlags(xfer_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                xfer_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                # Use live transfer color
                theme_mode = mw._current_theme_mode
                xfer_item.setForeground(QColor(173, 216, 255, 255) if theme_mode == 'dark' else QColor(20, 90, 150, 255))
                mw.gallery_table.setItem(matched_row, GalleryTableWidget.COL_TRANSFER, xfer_item)

            # Handle completion when all images uploaded OR progress reaches 100%
            if completed >= total or progress_percent >= 100:
                # Set finished timestamp if not already set
                if not item.finished_time:
                    item.finished_time = time.time()

                # If there were failures (based on item.uploaded_images vs total), show Failed; else Completed
                final_status_text = "Completed"
                row_failed = False
                if item.total_images and item.uploaded_images is not None and item.uploaded_images < item.total_images:
                    final_status_text = "Failed"
                    row_failed = True
                item.status = "completed" if not row_failed else "failed"
                # Final icon and text
                mw._set_status_cell_icon(matched_row, item.status)
                mw._set_status_text_cell(matched_row, item.status)

                # Update action buttons for completed status
                action_widget = mw.gallery_table.cellWidget(matched_row, GalleryTableWidget.COL_ACTION)
                if isinstance(action_widget, ActionButtonWidget):
                    action_widget.update_buttons(item.status)

                # Update finished time column
                from src.gui.main_window import format_timestamp_for_display
                finished_text, finished_tooltip = format_timestamp_for_display(item.finished_time)
                finished_item = QTableWidgetItem(finished_text)
                finished_item.setFlags(finished_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                finished_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if finished_tooltip:
                    finished_item.setToolTip(finished_tooltip)
                    pass
                mw.gallery_table.setItem(matched_row, GalleryTableWidget.COL_FINISHED, finished_item)

                # Compute and freeze final transfer speed for this item
                try:
                    elapsed = max(float(item.finished_time or time.time()) - float(item.start_time or item.finished_time), 0.001)
                    item.final_kibps = (float(getattr(item, 'uploaded_bytes', 0) or 0) / elapsed) / 1024.0
                    item.current_kibps = 0.0
                except Exception as e:
                    log(f"Exception in main_window: {e}", level="error", category="ui")
                    raise

                # Render Transfer column (10) - use cached function
                try:
                    if hasattr(mw, '_format_binary_rate'):
                        final_text = mw._format_binary_rate(item.final_kibps, precision=1) if item.final_kibps > 0 else ""
                    else:
                        final_text = f"{item.final_kibps:.1f} KiB/s" if item.final_kibps > 0 else ""
                except Exception as e:
                    log(f"Final rate formatting failed: {e}", level="warning", category="ui")
                    final_text = ""
                xfer_item = QTableWidgetItem(final_text)
                xfer_item.setFlags(xfer_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                xfer_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                try:
                    if final_text:
                        xfer_item.setForeground(QColor(0, 0, 0, 160))
                except Exception as e:
                    log(f"ERROR: Exception in main_window: {e}", level="error", category="ui")
                    raise
                mw.gallery_table.setItem(matched_row, GalleryTableWidget.COL_TRANSFER, xfer_item)

            # Update overall progress bar and info/speed displays after individual table updates
            mw.progress_tracker.update_progress_display()

        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise  # Fail silently to prevent blocking

    def on_gallery_completed(self, path: str, results: dict):
        """Handle gallery completion - minimal GUI thread work, everything else deferred"""
        mw = self._main_window
        # ONLY critical GUI updates on the main thread - keep this minimal!
        with QMutexLocker(mw.queue_manager.mutex):
            if path in mw.queue_manager.items:
                item = mw.queue_manager.items[path]
                # Essential status update only
                total = int(results.get('total_images') or 0)
                success = int(results.get('successful_count') or len(results.get('images', [])))
                item.total_images = total or item.total_images
                item.uploaded_images = success
                is_success = success >= (total or success)
                item.status = "completed" if is_success else "failed"
                item.progress = 100 if is_success else int((success / max(total, 1)) * 100)
                item.gallery_url = results.get('gallery_url', '')
                item.gallery_id = results.get('gallery_id', '')
                # Ensure failed galleries have error details from engine results
                if not is_success:
                    failed_details = results.get('failed_details', [])
                    failed_count = int(results.get('failed_count') or 0)
                    if failed_details and not item.failed_files:
                        item.failed_files = failed_details
                    if not item.error_message and failed_count:
                        item.error_message = f"{failed_count} of {total} images failed to upload"
                item.finished_time = time.time()
                # Quick transfer rate calculation
                try:
                    elapsed = max(float(item.finished_time or time.time()) - float(item.start_time or item.finished_time), 0.001)
                    item.final_kibps = (float(results.get('uploaded_size', 0) or 0) / elapsed) / 1024.0
                    item.current_kibps = 0.0
                except Exception as e:
                    log(f"ERROR: Exception in main_window: {e}", level="error", category="ui")
                    raise

        # Check for file host auto-upload triggers (on_completed)
        try:
            from src.core.file_host_config import get_config_manager
            config_manager = get_config_manager()
            triggered_hosts = config_manager.get_hosts_by_trigger('completed')

            if triggered_hosts:
                log(f"Gallery completed trigger: Found {len(triggered_hosts)} enabled hosts with 'On Completed' trigger",
                    level="info", category="file_hosts")

                for host_id, host_config in triggered_hosts.items():
                    # Queue upload to this file host (use host_id, not display name)
                    upload_id = mw.queue_manager.store.add_file_host_upload(
                        gallery_path=path,
                        host_name=host_id,  # host_id like 'filedot', not display name
                        status='pending'
                    )

                    if upload_id:
                        log(f"Queued file host upload for {path} to {host_config.name} (upload_id={upload_id})", level="info", category="file_hosts")
                        mw.worker_signal_handler._update_filehost_queue_for_host(host_id)
                    else:
                        log(f"Failed to queue file host upload for {path} to {host_config.name}", level="error", category="file_hosts")
        except Exception as e:
            log(f"Error checking file host triggers on gallery completion: {e}", level="error", category="file_hosts")

        # Force final progress update to show 100% completion
        if path in mw.queue_manager.items:
            final_item = mw.queue_manager.items[path]
            mw._progress_batcher.add_update(path, final_item.uploaded_images, final_item.total_images, 100, "")

        # Cleanup temp folder if from archive
        if path in mw.queue_manager.items:
            itm = mw.queue_manager.items[path]
            if getattr(itm, 'is_from_archive', False):
                QTimer.singleShot(0, lambda p=path: mw.archive_coordinator.service.cleanup_temp_dir(p))

        # Delegate heavy file I/O to background thread immediately
        mw.completion_worker.process_completion(path, results, mw)

        # Handle other completion work synchronously to avoid UI race conditions
        self._handle_completion_immediate(path, results)

    def _handle_completion_immediate(self, path: str, results: dict):
        """Handle completion work immediately on GUI thread to maintain UI consistency"""
        mw = self._main_window
        # Core engine already logs upload completion details, no need to duplicate

        # Update current transfer speed immediately
        try:
            transfer_speed = float(results.get('transfer_speed', 0) or 0)
            mw.progress_tracker._current_transfer_kbps = transfer_speed / 1024.0
            # Also update the item's speed for consistency
            with QMutexLocker(mw.queue_manager.mutex):
                if path in mw.queue_manager.items:
                    item = mw.queue_manager.items[path]
                    item.final_kibps = mw.progress_tracker._current_transfer_kbps
        except Exception as e:
            log(f"ERROR: Exception in main_window: {e}", level="error", category="ui")
            raise

        # Re-enable settings if no remaining active items (defer to avoid blocking)
        #QTimer.singleShot(5, self._check_and_enable_settings)

        # Update display with targeted update instead of full rebuild
        mw._update_specific_gallery_display(path)

        # Auto-clear completed gallery if enabled
        from src.utils.paths import load_user_defaults
        defaults = load_user_defaults()
        if defaults.get('auto_clear_completed', False):
            # Get item to check if it's actually completed (not failed)
            item = mw.queue_manager.get_item(path)
            if item and item.status == "completed":
                QTimer.singleShot(100, lambda: mw._remove_gallery_from_table(path))


        # Update button counts and progress after status change
        QTimer.singleShot(0, mw.progress_tracker._update_counts_and_progress)

        # Defer only the heavy stats update to avoid blocking
        QTimer.singleShot(50, lambda: self._update_stats_deferred(results))

        # Fire notification
        if hasattr(mw, 'notification_manager'):
            mw.notification_manager.notify('gallery_completed')

    def _update_stats_deferred(self, results: dict):
        """Update cumulative stats in background"""
        mw = self._main_window
        try:
            successful_count = results.get('successful_count', 0)
            settings = QSettings("BBDropUploader", "Stats")
            total_galleries = settings.value("total_galleries", 0, type=int) + 1
            total_images_acc = settings.value("total_images", 0, type=int) + successful_count
            base_total_str = settings.value("total_size_bytes_v2", "0")
            try:
                base_total = int(str(base_total_str))
            except Exception as e:
                log(f"Failed to parse total_size_bytes_v2: {e}", level="warning", category="stats")
                base_total = settings.value("total_size_bytes", 0, type=int)
            total_size_acc = base_total + int(results.get('uploaded_size', 0) or 0)
            transfer_speed = float(results.get('transfer_speed', 0) or 0)
            current_kbps = transfer_speed / 1024.0
            fastest_kbps = settings.value("fastest_kbps", 0.0, type=float)
            if current_kbps > fastest_kbps:
                fastest_kbps = current_kbps
                # Save timestamp when new record is set
                from datetime import datetime
                settings.setValue("fastest_kbps_timestamp",
                                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            settings.setValue("total_galleries", total_galleries)
            settings.setValue("total_images", total_images_acc)
            settings.setValue("total_size_bytes_v2", str(total_size_acc))
            settings.setValue("fastest_kbps", fastest_kbps)
            settings.sync()
            # Refresh progress display to show updated stats
            mw.progress_tracker.update_progress_display()
        except Exception as e:
            log(f"ERROR: Exception in main_window: {e}", level="error", category="ui")
            raise

    def on_ext_fields_updated(self, path: str, ext_fields: dict):
        """Handle ext fields update from external hooks"""
        mw = self._main_window
        try:
            log(f"on_ext_fields_updated called: path={path}, ext_fields={ext_fields}", level="info", category="hooks")

            # Update the item in the queue manager (already done by worker)
            # Just need to refresh the table row to show the new values
            with QMutexLocker(mw.queue_manager.mutex):
                if path in mw.queue_manager.items:
                    item = mw.queue_manager.items[path]
                    log(f"Found item in queue_manager: {item.name}", level="debug", category="hooks")

                    # Get the actual table widget - SAME PATTERN AS _populate_table_row
                    actual_table = getattr(mw.gallery_table, 'table', mw.gallery_table)
                    log(f"Using actual_table: {type(actual_table).__name__}", level="debug", category="hooks")

                    # Use O(1) path lookup instead of O(n) row iteration
                    row = mw._get_row_for_path(path)
                    if row is not None and actual_table:
                        log(f"Found matching row {row} for path {path}", level="debug", category="hooks")

                        # Block signals to prevent itemChanged events during update
                        signals_blocked = actual_table.signalsBlocked()
                        actual_table.blockSignals(True)
                        try:
                            # Update ext columns
                            for ext_field, value in ext_fields.items():
                                log(f"Processing ext_field={ext_field}, value={value}", level="debug", category="hooks")
                                if ext_field == 'ext1':
                                    ext_item = QTableWidgetItem(str(value))
                                    ext_item.setFlags(ext_item.flags() | Qt.ItemFlag.ItemIsEditable)
                                    ext_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                                    actual_table.setItem(row, GalleryTableWidget.COL_EXT1, ext_item)
                                    log(f"Set COL_EXT1 (col {GalleryTableWidget.COL_EXT1}) to: {value}", level="trace", category="hooks")
                                elif ext_field == 'ext2':
                                    ext_item = QTableWidgetItem(str(value))
                                    ext_item.setFlags(ext_item.flags() | Qt.ItemFlag.ItemIsEditable)
                                    ext_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                                    actual_table.setItem(row, GalleryTableWidget.COL_EXT2, ext_item)
                                    log(f"Set COL_EXT2 (col {GalleryTableWidget.COL_EXT2}) to: {value}", level="trace", category="hooks")
                                elif ext_field == 'ext3':
                                    ext_item = QTableWidgetItem(str(value))
                                    ext_item.setFlags(ext_item.flags() | Qt.ItemFlag.ItemIsEditable)
                                    ext_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                                    actual_table.setItem(row, GalleryTableWidget.COL_EXT3, ext_item)
                                    log(f"Set COL_EXT3 (col {GalleryTableWidget.COL_EXT3}) to: {value}", level="trace", category="hooks")
                                elif ext_field == 'ext4':
                                    ext_item = QTableWidgetItem(str(value))
                                    ext_item.setFlags(ext_item.flags() | Qt.ItemFlag.ItemIsEditable)
                                    ext_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                                    actual_table.setItem(row, GalleryTableWidget.COL_EXT4, ext_item)
                                    log(f"Set COL_EXT4 (col {GalleryTableWidget.COL_EXT4}) to: {value}", level="trace", category="hooks")
                        finally:
                            # Restore original signal state
                            actual_table.blockSignals(signals_blocked)

                        log(f"Updated ext fields in GUI for {item.name}: {ext_fields}", level="info", category="hooks")
                        # Trigger artifact regeneration for ext field changes if enabled
                        def _maybe_regen(p=path):
                            if mw.artifact_handler.should_auto_regenerate_bbcode(p):
                                mw.artifact_handler.regenerate_bbcode_for_gallery(
                                    p, force=False
                                )
                        QTimer.singleShot(100, _maybe_regen)
                    elif not actual_table:
                        log(f"WARNING: Table is None!", level="debug", category="hooks")
                else:
                    log(f"Path {path} not found in queue_manager.items", level="debug", category="hooks")
        except Exception as e:
            log(f"Error updating ext fields in GUI: {e}", level="error", category="hooks")
            import traceback
            traceback.print_exc()


    def on_completion_processed(self, path: str):
        """Handle when background completion processing is done"""
        # Background file generation is complete, nothing specific needed here
        # but could trigger additional UI updates if needed in the future
        pass


    def on_gallery_exists(self, gallery_name: str, existing_files: list):
        """Handle existing gallery detection"""
        mw = self._main_window
        json_count = sum(1 for f in existing_files if f.lower().endswith('.json'))
        message = f"Gallery '{gallery_name}' already exists with {json_count} .json file{'' if json_count == 1 else 's'}.\n\nContinue with upload anyway?"
        msgbox = QMessageBox(mw)
        msgbox.setWindowTitle("Gallery Already Exists")
        msgbox.setText(message)
        msgbox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msgbox.setDefaultButton(QMessageBox.StandardButton.No)
        msgbox.open()
        msgbox.finished.connect(lambda result: self._handle_upload_gallery_exists_confirmation(result))

    def _handle_upload_gallery_exists_confirmation(self, result):
        """Handle upload gallery exists confirmation"""
        if result != QMessageBox.StandardButton.Yes:
            # Cancel the upload
            log(f"Upload cancelled by user due to existing gallery", level="info", category="ui")
            # TODO: Implement proper cancellation mechanism
        else:
            log("User chose to continue with existing gallery", level="info", category="ui")

    def on_gallery_renamed(self, gallery_id: str):
        """Mark cells for the given gallery_id as renamed (check icon) - optimized version."""
        mw = self._main_window
        # Update unnamed gallery count
        mw.progress_tracker._update_unnamed_count_background()
        # Defer the expensive operation to avoid blocking GUI
        QTimer.singleShot(1, lambda: self._handle_gallery_renamed_background(gallery_id))

    def _handle_gallery_renamed_background(self, gallery_id: str):
        """Handle gallery renamed in background to avoid blocking"""
        mw = self._main_window
        try:
            # Find the gallery by ID using path mapping instead of full traversal
            found_row = None
            item = None
            for path, row in mw.path_to_row.items():
                item = mw.queue_manager.get_item(path)
                if item and item.gallery_id == gallery_id:
                    found_row = row
                    break

            if found_row is not None and item is not None:
                # Guard: only mark renamed for hosts that support gallery rename
                host_id = getattr(item, 'image_host_id', 'imx') or 'imx'
                if host_id == 'imx':
                    mw._set_renamed_cell_icon(found_row, True)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

    def on_gallery_failed(self, path: str, error_message: str):
        """Handle gallery failure"""
        mw = self._main_window
        with QMutexLocker(mw.queue_manager.mutex):
            if path in mw.queue_manager.items:
                item = mw.queue_manager.items[path]
                item.status = "failed"
                item.error_message = error_message

        # Re-enable settings if no remaining active (queued/uploading) items
        #try:
        #    remaining = mw.queue_manager.get_all_items()
        #    any_active = any(i.status in ("queued", "uploading") for i in remaining)
        #    mw.settings_group.setEnabled(not any_active)
        #except Exception as e:
        #    log(f"ERROR: Exception in main_window: {e}", level="error", category="ui")
        #    raise

        # Update display when status changes
        mw._update_specific_gallery_display(path)

        # Update button counts and progress after status change
        QTimer.singleShot(0, mw.progress_tracker._update_counts_and_progress)

        gallery_name = os.path.basename(path)
        log(f"Failed: {gallery_name} - {error_message}", level="warning")

        # Fire notification
        if hasattr(mw, 'notification_manager'):
            mw.notification_manager.notify('gallery_failed', detail=error_message[:80])
