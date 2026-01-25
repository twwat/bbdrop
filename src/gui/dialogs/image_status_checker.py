#!/usr/bin/env python3
"""
Image Status Checker

Coordinates checking image online status on IMX.to for galleries.
Handles dialog display, worker callbacks, and database updates.
"""

import os
import threading
import time
from datetime import datetime
from typing import List, Optional, Any, TYPE_CHECKING

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import QWidget, QMessageBox

from src.gui.dialogs.image_status_dialog import ImageStatusDialog
from src.utils.logger import log

if TYPE_CHECKING:
    from src.gui.widgets.gallery_table import GalleryTableWidget


class ImageStatusChecker:
    """Coordinates image status checking for galleries.

    This class handles:
    - Gathering gallery data and image URLs from the queue manager
    - Displaying the ImageStatusDialog
    - Setting up callbacks for the rename worker
    - Updating the database and gallery table with results
    """

    def __init__(
        self,
        parent: QWidget,
        queue_manager: Any,
        rename_worker: Any,
        gallery_table: "GalleryTableWidget"
    ):
        """Initialize the status checker.

        Args:
            parent: Parent widget for dialogs
            queue_manager: Queue manager instance for database access
            rename_worker: RenameWorker instance for status checking
            gallery_table: Gallery table widget for display updates
        """
        self.parent = parent
        self.queue_manager = queue_manager
        self.rename_worker = rename_worker
        self.gallery_table = gallery_table
        self.dialog: Optional[ImageStatusDialog] = None

        # Thread-safety lock for state variables accessed cross-thread
        # Protects: _check_in_progress, _cancelled, _start_time, _galleries_data
        self._state_lock = threading.Lock()

        # State tracking for decoupled results
        self._check_in_progress = False
        self._cancelled = False  # Prevents race between _on_cancel() and _on_completed()
        self._galleries_data: List[dict] = []  # Store for result application
        self._start_time = 0.0  # For timing

    def check_galleries(self, paths: List[str]) -> None:
        """Check image status for the specified gallery paths.

        Args:
            paths: List of gallery paths to check
        """
        if not paths:
            return

        if self.dialog is not None and self.dialog.isVisible():
            return  # Already checking

        _preprocess_start = time.perf_counter()
        log(f"DEBUG TIMING: check_galleries started with {len(paths)} paths",
            level="debug", category="status_check")

        # Batch pre-processing: Get all items first (O(n) total instead of O(n) per path)
        _t_items_start = time.perf_counter()
        items = {path: self.queue_manager.get_item(path) for path in paths}
        _t_items_end = time.perf_counter()
        log(f"DEBUG TIMING: Get items took {(_t_items_end - _t_items_start)*1000:.1f}ms",
            level="debug", category="status_check")

        # Filter to completed galleries only
        completed_paths = [path for path, item in items.items()
                          if item and item.status == "completed"]

        if not completed_paths:
            QMessageBox.information(
                self.parent, "No Images",
                "No completed galleries found in selection."
            )
            return

        # Single batch query for all image URLs (much more efficient)
        _t_urls_start = time.perf_counter()
        all_image_urls = self.queue_manager.store.get_image_urls_for_galleries(completed_paths)
        _t_urls_end = time.perf_counter()
        log(f"DEBUG TIMING: get_image_urls_for_galleries took {(_t_urls_end - _t_urls_start)*1000:.1f}ms for {len(completed_paths)} paths",
            level="debug", category="status_check")

        # Build galleries_data from batch results
        _t_build_start = time.perf_counter()
        galleries_data = []
        for path in completed_paths:
            item = items[path]
            urls = [img['url'] for img in all_image_urls.get(path, []) if img.get('url')]
            if urls:
                galleries_data.append({
                    'db_id': item.db_id,
                    'path': path,
                    'name': item.name or os.path.basename(path),
                    'total_images': len(urls),
                    'image_urls': urls
                })

        _t_build_end = time.perf_counter()
        log(f"DEBUG TIMING: Build galleries_data took {(_t_build_end - _t_build_start)*1000:.1f}ms",
            level="debug", category="status_check")
        _preprocess_end = time.perf_counter()
        log(f"DEBUG TIMING: Total preprocessing took {(_preprocess_end - _preprocess_start)*1000:.1f}ms",
            level="debug", category="status_check")

        if not galleries_data:
            QMessageBox.information(
                self.parent, "No Images",
                "No image URLs found for the selected galleries."
            )
            return

        # Store data for result application and timing (thread-safe)
        with self._state_lock:
            self._galleries_data = galleries_data
            self._start_time = time.time()
            self._check_in_progress = True
            self._cancelled = False

        # Log the start of the check with details
        total_images = sum(g['total_images'] for g in galleries_data)
        log(f"Checking online status of {total_images} images ({len(galleries_data)} galleries) on imx.to",
            level="info", category="status_check")

        # Create and show dialog
        self.dialog = ImageStatusDialog(self.parent)
        self.dialog.set_galleries(galleries_data)
        self.dialog.show_progress(True)
        self.dialog.show()

        # Connect dialog finished signal for cleanup when closed
        self.dialog.finished.connect(self._on_dialog_finished)

        # Connect cancel signal
        self.dialog.cancelled.connect(self._on_cancel)

        # Connect signals for thread-safe cross-thread communication
        # Use explicit QueuedConnection for cross-thread safety
        self.rename_worker.status_check_progress.connect(
            self._on_progress, Qt.ConnectionType.QueuedConnection)
        self.rename_worker.status_check_completed.connect(
            self._on_completed, Qt.ConnectionType.QueuedConnection)
        self.rename_worker.status_check_error.connect(
            self._on_error, Qt.ConnectionType.QueuedConnection)
        self.rename_worker.quick_count_available.connect(
            self._on_quick_count, Qt.ConnectionType.QueuedConnection)

        # Start the check
        self.rename_worker.check_image_status(galleries_data)

    def _cleanup_connections(self) -> None:
        """Disconnect signal connections to prevent memory leaks."""
        try:
            self.rename_worker.status_check_progress.disconnect(self._on_progress)
            self.rename_worker.status_check_completed.disconnect(self._on_completed)
            self.rename_worker.status_check_error.disconnect(self._on_error)
            self.rename_worker.quick_count_available.disconnect(self._on_quick_count)
        except TypeError:
            # Signals already disconnected
            pass

    def _on_dialog_finished(self, result: int) -> None:
        """Handle dialog close - cleanup depends on check state.

        Cleanup responsibility flow:
        - If check NOT in progress: cleanup signals here immediately
        - If check IS in progress: _on_completed() or _on_error() will handle cleanup
          when the worker finishes (ensures results are still processed)

        Args:
            result: Dialog result code (ignored)
        """
        with self._state_lock:
            check_running = self._check_in_progress

        if check_running:
            # Dialog closed but check still running - keep signals connected
            # _on_completed() or _on_error() will handle cleanup when worker finishes
            self.dialog = None
            log("Dialog closed - check will continue in background", level="debug", category="status_check")
        else:
            # Check already complete, safe to cleanup
            self._cleanup_connections()
            self.dialog = None

    def _on_progress(self, current: int, total: int) -> None:
        """Handle progress updates from the worker.

        Args:
            current: Current progress value
            total: Total progress value
        """
        if self.dialog:
            self.dialog.update_progress(current, total)

    def _on_quick_count(self, online: int, total: int) -> None:
        """Handle quick count result from the worker.

        Called as soon as "Found: X images" is parsed (2-3 seconds).

        Args:
            online: Number of images found online
            total: Total images submitted for checking
        """
        log(f"Quick count: {online}/{total} images online",
            level="info", category="status_check")

        if self.dialog:
            self.dialog.show_quick_count(online, total)

    def _on_completed(self, results: dict) -> None:
        """Handle completion of status check.

        This method handles cleanup when check completes (successfully or after dialog closed).
        Results are applied to database and table unless the check was cancelled.

        Cleanup responsibility:
        - This method ALWAYS cleans up signal connections when called
        - If cancelled: discard results, just cleanup
        - If not cancelled: process results, update DB/table, then cleanup

        Args:
            results: Dict keyed by gallery path with status results
        """
        # Thread-safe state access - check if cancelled and get timing info
        with self._state_lock:
            if self._cancelled:
                # Check was cancelled, don't process results
                self._check_in_progress = False
                log("Status check results discarded (cancelled)", level="debug", category="status_check")
                self._cleanup_connections()
                return

            elapsed = time.time() - self._start_time
            self._check_in_progress = False

        _t0 = time.perf_counter()
        log(f"DEBUG TIMING: _on_completed started, received {len(results)} gallery results",
            level="debug", category="status_check")

        # Calculate aggregates for logging
        total_images = 0
        total_online = 0
        galleries_online = 0
        galleries_partial = 0
        galleries_offline = 0
        total_galleries = len(results)

        for result in results.values():
            online = result.get('online', 0)
            total = result.get('total', 0)
            total_images += total
            total_online += online

            if total > 0:
                if online == total:
                    galleries_online += 1
                elif online == 0:
                    galleries_offline += 1
                else:
                    galleries_partial += 1

        _t1 = time.perf_counter()
        log(f"DEBUG TIMING: Aggregate calculation took {(_t1 - _t0)*1000:.1f}ms",
            level="debug", category="status_check")

        # Log detailed completion message
        img_pct = (total_online * 100 // total_images) if total_images > 0 else 0
        gal_pct = (galleries_online * 100 // total_galleries) if total_galleries > 0 else 0
        rate = total_images / elapsed if elapsed > 0 else 0
        log(f"Found online on imx.to: {total_online}/{total_images} images ({img_pct}%), "
            f"{galleries_online}/{total_galleries} galleries ({gal_pct}%) "
            f"-- took {elapsed:.1f}sec ({rate:.0f} images/sec)",
            level="info", category="status_check")

        # Update lifetime checker statistics
        images_offline = total_images - total_online
        self._update_checker_stats(
            galleries_online=galleries_online,
            galleries_offline=galleries_offline,
            galleries_partial=galleries_partial,
            images_online=total_online,
            images_offline=images_offline
        )

        # Update dialog only if it still exists
        if self.dialog:
            _t2 = time.perf_counter()
            self.dialog.set_results(results, elapsed)
            _t3 = time.perf_counter()
            log(f"DEBUG TIMING: dialog.set_results took {(_t3 - _t2)*1000:.1f}ms",
                level="debug", category="status_check")

        # ALWAYS update database and table (even if dialog was closed)
        check_timestamp = int(time.time())
        check_datetime = time.strftime("%Y-%m-%d %H:%M", time.localtime(check_timestamp))

        # Build path-to-row index for O(1) lookups (instead of O(n) per gallery)
        # NOTE: This O(n) iteration over table rows runs in the main/UI thread intentionally
        # for simplicity. This is acceptable for typical use cases of <2000 galleries where
        # the iteration completes in <10ms. For larger datasets, consider moving to a
        # background thread or maintaining a persistent path-to-row cache.
        _t4 = time.perf_counter()
        path_to_row = {}
        for row in range(self.gallery_table.rowCount()):
            item = self.gallery_table.item(row, self.gallery_table.COL_NAME)
            if item:
                path_to_row[item.data(Qt.ItemDataRole.UserRole)] = row
        _t5 = time.perf_counter()
        log(f"DEBUG TIMING: Build path_to_row index took {(_t5 - _t4)*1000:.1f}ms for {self.gallery_table.rowCount()} rows",
            level="debug", category="status_check")

        # Collect all database updates for batch write
        _t6 = time.perf_counter()
        db_updates = []
        for path, result in results.items():
            online = result.get('online', 0)
            total = result.get('total', 0)

            # Build status text
            if total == 0:
                status_text = ""
            elif online == total:
                status_text = f"Online ({online}/{total})"
            elif online == 0:
                status_text = f"Offline (0/{total})"
            else:
                status_text = f"Partial ({online}/{total})"

            db_updates.append((path, status_text, check_timestamp))

            # O(1) lookup instead of O(n) search per gallery
            row = path_to_row.get(path)
            if row is not None:
                self.gallery_table.set_online_imx_status(row, online, total, check_datetime)

        _t7 = time.perf_counter()
        log(f"DEBUG TIMING: Process results + table updates took {(_t7 - _t6)*1000:.1f}ms for {len(results)} galleries",
            level="debug", category="status_check")

        # Single batch database write (much more efficient than N individual writes)
        if db_updates:
            _t8 = time.perf_counter()
            try:
                self.queue_manager.store.bulk_update_gallery_imx_status(db_updates)
            except Exception as e:
                log(f"Failed to update imx status in database: {e}",
                    level="error", category="status_check")
            _t9 = time.perf_counter()
            log(f"DEBUG TIMING: Bulk DB update took {(_t9 - _t8)*1000:.1f}ms for {len(db_updates)} updates",
                level="debug", category="status_check")

        _t10 = time.perf_counter()
        log(f"DEBUG TIMING: Total _on_completed processing took {(_t10 - _t0)*1000:.1f}ms",
            level="debug", category="status_check")

        # Cleanup signal connections at the very end
        self._cleanup_connections()
        # Only clear dialog reference if it hasn't already been cleared by _on_dialog_finished
        if self.dialog is not None:
            self.dialog = None

    def _on_error(self, error_msg: str) -> None:
        """Handle error from the worker.

        Cleanup responsibility:
        - This method ALWAYS cleans up signal connections when called
        - Marks check as no longer in progress

        Args:
            error_msg: Error message string
        """
        with self._state_lock:
            self._check_in_progress = False

        log(f"Image status check failed: {error_msg}", level="error", category="status_check")

        if self.dialog:
            self.dialog.show_progress(False)
            QMessageBox.critical(
                self.parent, "Check Failed",
                f"Failed to check image status: {error_msg}"
            )

        # Cleanup signal connections
        self._cleanup_connections()
        # Only clear dialog reference if it hasn't already been cleared by _on_dialog_finished
        if self.dialog is not None:
            self.dialog = None

    def _on_cancel(self) -> None:
        """Handle cancel request from dialog.

        Sets the cancelled flag to prevent _on_completed() from processing results
        if the worker completes after cancel is requested (race condition prevention).
        """
        with self._state_lock:
            self._cancelled = True
            self._check_in_progress = False

        self.rename_worker.cancel_status_check()
        self._cleanup_connections()
        log("Image status check cancelled by user", level="info", category="status_check")

    def _update_checker_stats(
        self,
        galleries_online: int,
        galleries_offline: int,
        galleries_partial: int,
        images_online: int,
        images_offline: int
    ) -> None:
        """Update lifetime statistics for the online status checker.

        Persists cumulative totals and last-run details to QSettings.
        Called after each successful status check completion.

        Note: This method is non-critical and wrapped in try-except to
        ensure stats failures don't break the completion flow.

        Args:
            galleries_online: Count of fully online galleries in this scan
            galleries_offline: Count of fully offline galleries in this scan
            galleries_partial: Count of partial galleries in this scan
            images_online: Count of online images in this scan
            images_offline: Count of offline images in this scan
        """
        try:
            settings = QSettings("BBDropUploader", "Stats")

            # Update lifetime totals (cumulative)
            settings.setValue("checker_online_galleries",
                settings.value("checker_online_galleries", 0, type=int) + galleries_online)
            settings.setValue("checker_offline_galleries",
                settings.value("checker_offline_galleries", 0, type=int) + galleries_offline)
            settings.setValue("checker_partial_galleries",
                settings.value("checker_partial_galleries", 0, type=int) + galleries_partial)
            settings.setValue("checker_online_images",
                settings.value("checker_online_images", 0, type=int) + images_online)
            settings.setValue("checker_offline_images",
                settings.value("checker_offline_images", 0, type=int) + images_offline)
            settings.setValue("checker_total_scans",
                settings.value("checker_total_scans", 0, type=int) + 1)

            # Update last run details (overwritten each scan)
            settings.setValue("checker_last_timestamp",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            settings.setValue("checker_last_online_images", images_online)
            settings.setValue("checker_last_offline_images", images_offline)
            settings.setValue("checker_last_online_galleries", galleries_online)
            settings.setValue("checker_last_offline_galleries", galleries_offline)
            settings.setValue("checker_last_partial_galleries", galleries_partial)

            settings.sync()
        except Exception as e:
            log(f"Failed to update checker stats: {e}",
                level="warning", category="status_check")
