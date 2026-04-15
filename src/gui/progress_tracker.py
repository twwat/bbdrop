"""Progress tracking and bandwidth monitoring for BBDrop GUI.

This module handles all progress-related operations extracted from main_window.py
to improve maintainability and separation of concerns.
"""

import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, List, Tuple

from PyQt6.QtCore import QObject, QTimer, QSettings, Qt, QMutexLocker
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor

from src.utils.logger import log
from src.gui.widgets.gallery_table import GalleryTableWidget
from src.gui.widgets.custom_widgets import TableProgressWidget, ActionButtonWidget

if TYPE_CHECKING:
    from src.gui.main_window import BBDropGUI


def format_timestamp_for_display(timestamp_value, include_seconds=False):
    """Format Unix timestamp for table display."""
    if not timestamp_value:
        return "", ""
    try:
        dt = datetime.fromtimestamp(timestamp_value)
        display_text = dt.strftime("%Y-%m-%d %H:%M")
        tooltip_text = dt.strftime("%Y-%m-%d %H:%M:%S")
        return display_text, tooltip_text
    except (ValueError, OSError, OverflowError):
        return "", ""


class ProgressTracker(QObject):
    """Handles progress tracking and bandwidth monitoring for the main window."""

    def __init__(self, main_window: 'BBDropGUI'):
        """Initialize the ProgressTracker."""
        super().__init__()
        self._main_window = main_window
        self._current_transfer_kbps = 0.0
        self._bandwidth_samples = []

        # Cache QSettings instances to avoid disk/registry I/O on every call
        self._stats_settings = QSettings("BBDropUploader", "Stats")
        self._gui_settings = QSettings("BBDropUploader", "BBDropGUI")

        # Cache stats values with periodic refresh
        self._cached_stats: dict = {}
        self._stats_cache_time: float = 0.0

    def _get_cached_stats(self) -> dict:
        """Get cached statistics with periodic refresh (every 5 seconds).

        Returns:
            dict: Cached statistics including total_galleries, total_images,
                  total_size_bytes, fastest_kbps, and fastest_kbps_timestamp.
        """
        now = time.time()
        if now - self._stats_cache_time > 5.0:  # Refresh every 5s
            settings = self._stats_settings
            self._cached_stats = {
                'total_galleries': settings.value("total_galleries", 0, type=int),
                'total_images': settings.value("total_images", 0, type=int),
                'total_size_bytes_v2': settings.value("total_size_bytes_v2", "0"),
                'total_size_bytes': settings.value("total_size_bytes", 0, type=int),
                'fastest_kbps': settings.value("fastest_kbps", 0.0, type=float),
                'fastest_kbps_timestamp': settings.value("fastest_kbps_timestamp", ""),
            }
            self._stats_cache_time = now
        return self._cached_stats

    def _update_counts_and_progress(self):
        """Update both button counts and progress display together."""
        self._update_button_counts()
        self.update_progress_display()

    def _get_file_host_rows(self, item_path: str) -> list:
        try:
            store = self._main_window.queue_manager.store
        except Exception:
            return []
        try:
            return store.get_file_host_uploads(item_path) or []
        except Exception:
            return []

    def _compute_item_work_bytes(
        self, item, file_host_rows: list | None = None
    ) -> Tuple[int, int]:
        """Compute byte-weighted (total, uploaded) for a single item.

        Image host side:
            - video galleries contribute the screenshot sheet filesize (or a
              1% fallback of total_size if the sheet isn't readable)
            - image galleries contribute item.total_size
            - uploaded portion = image_host_total if item.status == 'completed',
              otherwise ratio * image_host_total from uploaded_images/total_images

        File host rows (from file_host_uploads table):
            - completed / deduped -> uploaded = effective_total
            - uploading / failed  -> uploaded = row.uploaded_bytes (capped)
            - anything else       -> uploaded = 0 but counted toward total

        ``effective_total`` for a row is max(row.total_bytes, row.file_size,
        item.total_size) so small or missing values don't inflate the percent.
        """
        is_video = getattr(item, 'media_type', 'image') == 'video'
        sheet_path = getattr(item, 'screenshot_sheet_path', '') or ''
        item_total_size = int(getattr(item, 'total_size', 0) or 0)

        if is_video and sheet_path:
            try:
                image_host_total = os.path.getsize(sheet_path) if os.path.exists(sheet_path) else 0
            except OSError:
                image_host_total = 0
            if image_host_total <= 0:
                image_host_total = max(1, item_total_size // 100)
        else:
            image_host_total = item_total_size

        status = getattr(item, 'status', '')
        if status == 'completed':
            image_host_uploaded = image_host_total
        elif status == 'uploading':
            total_images = int(getattr(item, 'total_images', 0) or 0)
            uploaded_images = int(getattr(item, 'uploaded_images', 0) or 0)
            if total_images > 0:
                ratio = min(1.0, uploaded_images / total_images)
                image_host_uploaded = int(image_host_total * ratio)
            else:
                image_host_uploaded = 0
        else:
            image_host_uploaded = 0

        total_bytes = image_host_total
        uploaded_bytes = image_host_uploaded

        if file_host_rows is None:
            file_host_rows = self._get_file_host_rows(getattr(item, 'path', ''))

        fallback_estimate = max(item_total_size, 1)

        for row in file_host_rows:
            row_status = row.get('status', '')
            row_total = int(row.get('total_bytes') or 0)
            row_uploaded = int(row.get('uploaded_bytes') or 0)
            row_deduped = bool(row.get('deduped'))
            row_file_size = int(row.get('file_size') or 0)

            # Cancelled/blocked rows are user-abandoned or permanently stuck
            # without intervention; excluding them from work means the bar
            # can still reach 100% on the rest of the gallery.
            if row_status in ('cancelled', 'blocked'):
                continue

            effective_total = max(row_total, row_file_size, fallback_estimate)

            if row_deduped or row_status == 'completed':
                total_bytes += effective_total
                uploaded_bytes += effective_total
            elif row_status in ('uploading', 'failed'):
                total_bytes += effective_total
                uploaded_bytes += min(row_uploaded, effective_total)
            else:
                total_bytes += effective_total

        return total_bytes, uploaded_bytes

    def _compute_work_bytes(self, items) -> Tuple[int, int]:
        """Sum byte-weighted work across items for the overall progress bar."""
        total_bytes = 0
        uploaded_bytes = 0
        for item in items:
            item_total, item_uploaded = self._compute_item_work_bytes(item)
            total_bytes += item_total
            uploaded_bytes += item_uploaded
        return total_bytes, uploaded_bytes

    def compute_item_display(self, item) -> Tuple[int, str]:
        """Return (percent, effective_status) for a per-row display.

        Percent is byte-weighted across image host + file host work, with a
        1% floor when any progress has been made (so small completed chunks
        aren't hidden). Effective status overrides item.status to 'uploading'
        when the image host is done but file host rows are still pending,
        uploading, or failed -- so the row doesn't prematurely read as
        "Completed" while large video/archive uploads are still in flight.
        """
        file_host_rows = self._get_file_host_rows(getattr(item, 'path', ''))
        total_bytes, uploaded_bytes = self._compute_item_work_bytes(item, file_host_rows)

        if total_bytes > 0:
            raw_percent = int((uploaded_bytes / total_bytes) * 100)
            if uploaded_bytes > 0 and raw_percent < 1:
                percent = 1
            else:
                percent = min(100, max(0, raw_percent))
            if uploaded_bytes >= total_bytes:
                percent = 100
        else:
            percent = int(getattr(item, 'progress', 0) or 0)

        base_status = getattr(item, 'status', '')
        effective_status = base_status
        if base_status == 'completed' and file_host_rows:
            # Cancelled/blocked rows count as terminal here even though they
            # aren't 'done' in the success sense -- the gallery shouldn't
            # stay stuck at "uploading" forever waiting on work that won't
            # happen.
            terminal_statuses = {'completed', 'cancelled', 'blocked'}
            all_done = all(
                bool(row.get('deduped')) or row.get('status') in terminal_statuses
                for row in file_host_rows
            )
            if not all_done:
                effective_status = 'uploading'
                # Keep percent under 100 while work is still in flight so the
                # bar doesn't look stuck-at-full with a spinner.
                if percent >= 100:
                    percent = 99

        return percent, effective_status

    def refresh_row_display(self, path: str):
        """Refresh the per-row progress bar, status icon/text, and action
        buttons for one gallery using byte-weighted effective state.

        Safe to call from lifecycle signal handlers on the GUI thread; the
        method early-exits cleanly if the row or item can't be resolved.
        """
        if not path:
            return
        mw = self._main_window
        item = mw.queue_manager.get_item(path)
        if item is None:
            return
        row = mw._get_row_for_path(path)
        if row is None or row < 0 or row >= mw.gallery_table.rowCount():
            return

        try:
            percent, effective_status = self.compute_item_display(item)
        except Exception as e:
            log(f"compute_item_display failed for {path}: {e}",
                level="warning", category="ui")
            return

        try:
            progress_widget = mw.gallery_table.cellWidget(row, GalleryTableWidget.COL_PROGRESS)
            if isinstance(progress_widget, TableProgressWidget):
                progress_widget.update_progress(percent, effective_status)
        except Exception as e:
            log(f"Row progress widget refresh failed for {path}: {e}",
                level="warning", category="ui")

        try:
            mw._set_status_cell_icon(row, effective_status)
            mw._set_status_text_cell(row, effective_status)
        except Exception as e:
            log(f"Row status cell refresh failed for {path}: {e}",
                level="warning", category="ui")

        # Action buttons track the raw item.status (not effective_status) so
        # "View BBCode" stays available after the image host finishes, even
        # while file host uploads are still in flight.
        try:
            action_widget = mw.gallery_table.cellWidget(row, GalleryTableWidget.COL_ACTION)
            if isinstance(action_widget, ActionButtonWidget):
                action_widget.update_buttons(getattr(item, 'status', effective_status))
        except Exception as e:
            log(f"Row action button refresh failed for {path}: {e}",
                level="warning", category="ui")

    def _update_button_counts(self):
        """Update button counts and states based on currently visible items."""
        try:
            visible_items = []
            all_items = self._main_window.queue_manager.get_all_items()

            path_to_row = {}
            for row in range(self._main_window.gallery_table.rowCount()):
                name_item = self._main_window.gallery_table.item(row, GalleryTableWidget.COL_NAME)
                if name_item:
                    path = name_item.data(Qt.ItemDataRole.UserRole)
                    if path:
                        path_to_row[path] = row

            for item in all_items:
                row = path_to_row.get(item.path)
                if row is not None and not self._main_window.gallery_table.isRowHidden(row):
                    visible_items.append(item)

            count_startable = sum(1 for item in visible_items if item.status in ("ready", "paused", "incomplete", "scanning"))
            count_pausable = sum(1 for item in visible_items if item.status in ("uploading", "queued"))
            count_completed = sum(1 for item in visible_items if item.status == "completed")

            self._main_window.start_all_btn.setText(" Start All " + (f"({count_startable})" if count_startable else ""))
            self._main_window.pause_all_btn.setText(" Pause All " + (f"({count_pausable})" if count_pausable else ""))
            self._main_window.clear_completed_btn.setText(" Clear Completed " + (f"({count_completed})" if count_completed else ""))

            self._main_window.start_all_btn.setEnabled(count_startable > 0)
            self._main_window.pause_all_btn.setEnabled(count_pausable > 0)
            self._main_window.clear_completed_btn.setEnabled(count_completed > 0)
        except Exception:
            pass

    def update_progress_display(self):
        """Update current tab progress and statistics."""
        items = self._main_window._get_current_tab_items()

        if not items:
            self._main_window.overall_progress.setValue(0)
            self._main_window.overall_progress.setText("Ready")
            self._main_window.overall_progress.setProgressProperty("status", "ready")
            current_tab_name = getattr(self._main_window.gallery_table, 'current_tab', 'All Tabs')
            self._main_window.stats_label.setText(f"No galleries in {current_tab_name}")
            return

        total_bytes, uploaded_bytes = self._compute_work_bytes(items)

        if total_bytes > 0:
            raw_percent = int((uploaded_bytes / total_bytes) * 100)
            if uploaded_bytes > 0 and raw_percent < 1:
                overall_percent = 1
            else:
                overall_percent = min(100, max(0, raw_percent))
            if uploaded_bytes >= total_bytes:
                overall_percent = 100
            uploaded_str = self._main_window._format_size_consistent(uploaded_bytes)
            total_str = self._main_window._format_size_consistent(total_bytes)
            self._main_window.overall_progress.setValue(overall_percent)
            self._main_window.overall_progress.setText(f"{overall_percent}% ({uploaded_str} / {total_str})")
            if overall_percent >= 100:
                self._main_window.overall_progress.setProgressProperty("status", "completed")
            else:
                self._main_window.overall_progress.setProgressProperty("status", "uploading")
        else:
            self._main_window.overall_progress.setValue(0)
            self._main_window.overall_progress.setText("Preparing...")
            self._main_window.overall_progress.setProgressProperty("status", "uploading")

        current_tab_name = getattr(self._main_window.gallery_table, 'current_tab', 'All Tabs')
        status_counts = {
            'uploading': sum(1 for item in items if item.status == 'uploading'),
            'queued': sum(1 for item in items if item.status == 'queued'),
            'completed': sum(1 for item in items if item.status == 'completed'),
            'ready': sum(1 for item in items if item.status in ('ready', 'paused', 'incomplete', 'scanning')),
            'failed': sum(1 for item in items if item.status == 'failed')
        }

        status_parts = []
        if status_counts['uploading'] > 0:
            status_parts.append(f"Uploading: {status_counts['uploading']}")
        if status_counts['queued'] > 0:
            status_parts.append(f"Queued: {status_counts['queued']}")
        if status_counts['completed'] > 0:
            status_parts.append(f"Completed: {status_counts['completed']}")
        if status_counts['ready'] > 0:
            status_parts.append(f"Ready: {status_counts['ready']}")
        if status_counts['failed'] > 0:
            status_parts.append(f"Error: {status_counts['failed']}")

        if status_parts:
            self._main_window.stats_label.setText(" | ".join(status_parts))
        else:
            self._main_window.stats_label.setText(f"No galleries in {current_tab_name}")

        QTimer.singleShot(100, self._update_unnamed_count_background)

        # Use cached stats to avoid disk/registry I/O on every progress update
        cached = self._get_cached_stats()
        total_galleries = cached['total_galleries']
        total_images_acc = cached['total_images']
        total_size_bytes_v2 = cached['total_size_bytes_v2']
        try:
            total_size_acc = int(str(total_size_bytes_v2))
        except Exception:
            total_size_acc = cached['total_size_bytes']
        fastest_kbps = cached['fastest_kbps']

        self._main_window.stats_total_galleries_value_label.setText(f"{total_galleries}")
        self._main_window.stats_total_images_value_label.setText(f"{total_images_acc}")
        total_size_str = self._main_window._format_size_consistent(total_size_acc)

        try:
            self._main_window.speed_transferred_value_label.setText(f"{total_size_str}")
            fastest_mib = fastest_kbps / 1024.0
            fastest_str = f"{fastest_mib:.3f} MiB/s"
            self._main_window.speed_fastest_value_label.setText(fastest_str)
            fastest_timestamp = cached['fastest_kbps_timestamp']
            if fastest_kbps > 0 and fastest_timestamp:
                self._main_window.speed_fastest_value_label.setToolTip(f"Record set: {fastest_timestamp}")
            else:
                self._main_window.speed_fastest_value_label.setToolTip("")
        except Exception as e:
            log(f"ERROR: Exception in progress_tracker: {e}", level="error", category="ui")

        all_items = self._main_window.queue_manager.get_all_items()
        uploading_count = sum(1 for item in all_items if item.status == "uploading")

        if uploading_count == 0:
            self._bandwidth_samples.clear()
            self._current_transfer_kbps = 0.0
            self._main_window.speed_current_value_label.setText("0.000 MiB/s")


    def _update_unnamed_count_background(self):
        """Update unnamed gallery count in background."""
        try:
            from src.storage.gallery_management import get_unnamed_galleries
            unnamed_galleries = get_unnamed_galleries()
            unnamed_count = len(unnamed_galleries)
            QTimer.singleShot(0, lambda: self._main_window.stats_unnamed_value_label.setText(f"{unnamed_count}"))
        except Exception:
            QTimer.singleShot(0, lambda: self._main_window.stats_unnamed_value_label.setText("0"))
