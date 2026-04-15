"""Gallery table operations controller for BBDrop GUI.

Handles gallery table add/remove operations, row-to-path mappings,
and interactive table events (cell clicks, template changes, host changes).
"""

import os
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QObject, QTimer, QMutexLocker, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

from src.utils.logger import log
from src.gui.widgets.gallery_table import GalleryTableWidget

if TYPE_CHECKING:
    from src.gui.main_window import BBDropGUI


class GalleryTableController(QObject):
    """Controls gallery table add/remove, path mappings, and interactive events."""

    def __init__(self, main_window: 'BBDropGUI'):
        super().__init__()
        self._main_window = main_window

    def _add_gallery_to_table(self, item):
        """Add a new gallery item to the table without rebuilding"""
        mw = self._main_window
        log(f"_add_gallery_to_table called for {item.path} with tab_name={item.tab_name}", level="debug", category="queue")

        # CRITICAL FIX: Check if path already exists in table to prevent duplicates
        if item.path in mw.path_to_row:
            existing_row = mw.path_to_row[item.path]
            log(f"Gallery already in table at row {existing_row}, updating instead of adding duplicate", level="debug", category="queue")
            # Update existing row instead of creating duplicate
            mw._populate_table_row(existing_row, item)
            return

        row = mw.gallery_table.rowCount()
        mw.gallery_table.setRowCount(row + 1)
        log(f"Adding NEW gallery to table at row {row}", level="debug", category="queue")

        # Update mappings
        mw.path_to_row[item.path] = row
        mw.row_to_path[row] = item.path

        # Initialize scan state tracking
        mw._last_scan_states[item.path] = item.scan_complete

        # Populate the new row
        mw._populate_table_row(row, item)

        # Make sure the row is visible if it belongs to the current tab
        current_tab = mw.gallery_table.current_tab if hasattr(mw.gallery_table, 'current_tab') else None
        if current_tab and (current_tab == "All Tabs" or item.tab_name == current_tab):
            mw.gallery_table.setRowHidden(row, False)
            log(f"Row {row} set VISIBLE for current tab '{current_tab}' (item tab: '{item.tab_name}')", level="trace", category="queue")
        else:
            mw.gallery_table.setRowHidden(row, True)
            log(f"Row {row} set HIDDEN - item tab '{item.tab_name}' != current tab '{current_tab}'", level="trace", category="queue")

        # Invalidate TabManager's cache for this tab so it reloads from database
        if hasattr(mw.gallery_table, 'tab_manager') and item.tab_name:
            mw.gallery_table.tab_manager.invalidate_tab_cache(item.tab_name)

        # CRITICAL FIX: Invalidate table update queue visibility cache so new visible rows get updates
        if hasattr(mw, '_table_update_queue') and mw._table_update_queue:
            mw._table_update_queue.invalidate_visibility_cache()

    def _remove_gallery_from_table(self, path: str):
        """Remove a gallery from the table and update mappings"""
        mw = self._main_window
        if path not in mw.path_to_row:
            return

        row_to_remove = mw.path_to_row[path]
        # Get the actual table (handle tabbed interface)
        table = mw.gallery_table
        if hasattr(mw.gallery_table, 'table'):
            table = mw.gallery_table.table
        table.removeRow(row_to_remove)

        # Update mappings - shift all rows after the removed one
        del mw.path_to_row[path]
        del mw.row_to_path[row_to_remove]

        # Clean up scan state tracking
        mw._last_scan_states.pop(path, None)

        # Shift mappings for all rows after the removed one
        new_path_to_row = {}
        new_row_to_path = {}
        for old_row, path_val in mw.row_to_path.items():
            new_row = old_row if old_row < row_to_remove else old_row - 1
            new_path_to_row[path_val] = new_row
            new_row_to_path[new_row] = path_val

        mw.path_to_row = new_path_to_row
        mw.row_to_path = new_row_to_path

    def _update_path_mappings_after_removal(self, removed_row: int):
        """Update path mappings after a row is removed"""
        mw = self._main_window
        # Remove the mapping for the removed row
        removed_path = mw.row_to_path.get(removed_row)
        if removed_path:
            mw.path_to_row.pop(removed_path, None)
        mw.row_to_path.pop(removed_row, None)

        # Shift all mappings for rows after the removed one
        new_path_to_row = {}
        new_row_to_path = {}

        for old_row, path in mw.row_to_path.items():
            new_row = old_row if old_row < removed_row else old_row - 1
            new_path_to_row[path] = new_row
            new_row_to_path[new_row] = path

        mw.path_to_row = new_path_to_row
        mw.row_to_path = new_row_to_path

    def _get_row_for_path(self, path: str) -> Optional[int]:
        """Thread-safe getter for path-to-row mapping"""
        mw = self._main_window
        with QMutexLocker(mw._path_mapping_mutex):
            return mw.path_to_row.get(path)

    def _set_path_row_mapping(self, path: str, row: int):
        """Thread-safe setter for path-to-row mapping"""
        mw = self._main_window
        with QMutexLocker(mw._path_mapping_mutex):
            mw.path_to_row[path] = row
            mw.row_to_path[row] = path

    def _rebuild_path_mappings(self):
        """Rebuild path mappings from current table state"""
        mw = self._main_window
        new_path_to_row = {}
        new_row_to_path = {}

        for row in range(mw.gallery_table.rowCount()):
            name_item = mw.gallery_table.item(row, GalleryTableWidget.COL_NAME)
            if name_item:
                path = name_item.data(Qt.ItemDataRole.UserRole)
                if path:
                    new_path_to_row[path] = row
                    new_row_to_path[row] = path

        with QMutexLocker(mw._path_mapping_mutex):
            mw.path_to_row = new_path_to_row
            mw.row_to_path = new_row_to_path

    def _update_specific_gallery_display(self, path: str, _retry_count: int = 0):
        """Update a specific gallery's display with background tab support - NON-BLOCKING"""
        mw = self._main_window
        item = mw.queue_manager.get_item(path)
        if not item:
            return

        # Get current font sizes

        # If item not in table, skip update (it should be added explicitly via add_folders)
        # This prevents duplicate additions via status change signals
        if path not in mw.path_to_row:
            # Item not yet in table - likely a race condition where scan completed
            # before the table row was created. Retry after a short delay.
            MAX_RETRIES = 10
            item = mw.queue_manager.get_item(path)
            if item and _retry_count < MAX_RETRIES:
                log(f"Item {path} not in path_to_row yet, scheduling retry {_retry_count + 1}/{MAX_RETRIES}",
                    level="debug", category="queue")
                QTimer.singleShot(100, lambda p=path, r=_retry_count: self._update_specific_gallery_display(p, r + 1))
            elif _retry_count >= MAX_RETRIES:
                log(f"Item {path} never added to table after {MAX_RETRIES} retries, giving up",
                    level="warning", category="queue")
            return

        # Check if row is currently visible for performance optimization
        row = mw.path_to_row.get(path)
        log(f"_update_specific_gallery_display: row={row}, in_mapping={path in mw.path_to_row}", level="trace", category="queue")
        if row is not None and 0 <= row < mw.gallery_table.rowCount():
            # Use table update queue for visible rows (includes hidden row filtering)
            if hasattr(mw, '_table_update_queue'):
                mw._table_update_queue.queue_update(path, item, 'full')
            else:
                log(f"No _table_update_queue, using direct update for row {row}", level="debug")
                # Fallback to direct update
                QTimer.singleShot(0, lambda: mw._populate_table_row(row, item))
        else:
            # If update fails, refresh filter as fallback
            log(f"Row update failed for {path}, refreshing filter", level="warning", category="queue")
            if hasattr(mw.gallery_table, 'refresh_filter'):
                QTimer.singleShot(0, mw.gallery_table.refresh_filter)

    def _populate_column_data(self, column_index: int):
        """Populate data for a specific column across all rows (used when showing hidden columns)"""
        mw = self._main_window

        # Get theme mode for styling
        theme_mode = mw._current_theme_mode

        # Get the actual table object
        actual_table = getattr(mw.gallery_table, 'table', mw.gallery_table)

        # Populate all rows in the table
        for row in range(mw.gallery_table.rowCount()):
            # Get the gallery path from row mapping
            path = mw.row_to_path.get(row)
            if not path:
                continue

            # Get the queue item for this row
            item = mw.queue_manager.get_item(path)
            if not item:
                continue

            # Populate based on column type
            if column_index == GalleryTableWidget.COL_STATUS_TEXT:
                # Status text column (5)
                mw._set_status_text_cell(row, item.status)

            elif column_index == GalleryTableWidget.COL_TRANSFER:
                # Transfer speed column (10)
                transfer_text = ""
                current_rate_kib = float(getattr(item, 'current_kibps', 0.0) or 0.0)
                final_rate_kib = float(getattr(item, 'final_kibps', 0.0) or 0.0)
                try:
                    from src.utils.format_utils import format_binary_rate
                    if item.status == "uploading" and current_rate_kib > 0:
                        transfer_text = format_binary_rate(current_rate_kib, precision=2)
                    elif final_rate_kib > 0:
                        transfer_text = format_binary_rate(final_rate_kib, precision=2)
                except Exception as e:
                    log(f"Rate formatting failed: {e}", level="warning", category="ui")
                    rate = current_rate_kib if item.status == "uploading" else final_rate_kib
                    transfer_text = mw._format_rate_consistent(rate) if rate > 0 else ""

                xfer_item = QTableWidgetItem(transfer_text)
                xfer_item.setFlags(xfer_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                xfer_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if item.status == "uploading" and transfer_text:
                    xfer_item.setForeground(QColor(173, 216, 255, 255) if theme_mode == 'dark' else QColor(20, 90, 150, 255))
                elif item.status in ("completed", "failed") and transfer_text:
                    xfer_item.setForeground(QColor(255, 255, 255, 230) if theme_mode == 'dark' else QColor(0, 0, 0, 190))
                mw.gallery_table.setItem(row, GalleryTableWidget.COL_TRANSFER, xfer_item)

            elif column_index == GalleryTableWidget.COL_GALLERY_ID:
                # Gallery ID column (13) - read-only
                signals_blocked = actual_table.signalsBlocked()
                actual_table.blockSignals(True)
                try:
                    gallery_id_text = item.gallery_id or ""
                    gallery_id_item = QTableWidgetItem(gallery_id_text)
                    gallery_id_item.setFlags(gallery_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    gallery_id_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    actual_table.setItem(row, GalleryTableWidget.COL_GALLERY_ID, gallery_id_item)
                finally:
                    actual_table.blockSignals(signals_blocked)

            elif GalleryTableWidget.COL_CUSTOM1 <= column_index <= GalleryTableWidget.COL_CUSTOM4:
                # Custom columns (14-17) - editable
                field_map = {
                    GalleryTableWidget.COL_CUSTOM1: 'custom1',
                    GalleryTableWidget.COL_CUSTOM2: 'custom2',
                    GalleryTableWidget.COL_CUSTOM3: 'custom3',
                    GalleryTableWidget.COL_CUSTOM4: 'custom4'
                }
                field_name = field_map.get(column_index)
                if field_name:
                    signals_blocked = actual_table.signalsBlocked()
                    actual_table.blockSignals(True)
                    try:
                        value = getattr(item, field_name, '') or ''
                        custom_item = QTableWidgetItem(str(value))
                        custom_item.setFlags(custom_item.flags() | Qt.ItemFlag.ItemIsEditable)
                        custom_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                        actual_table.setItem(row, column_index, custom_item)
                    finally:
                        actual_table.blockSignals(signals_blocked)

            elif GalleryTableWidget.COL_EXT1 <= column_index <= GalleryTableWidget.COL_EXT4:
                # Ext columns (18-21) - editable
                field_map = {
                    GalleryTableWidget.COL_EXT1: 'ext1',
                    GalleryTableWidget.COL_EXT2: 'ext2',
                    GalleryTableWidget.COL_EXT3: 'ext3',
                    GalleryTableWidget.COL_EXT4: 'ext4'
                }
                field_name = field_map.get(column_index)
                if field_name:
                    signals_blocked = actual_table.signalsBlocked()
                    actual_table.blockSignals(True)
                    try:
                        value = getattr(item, field_name, '') or ''
                        ext_item = QTableWidgetItem(str(value))
                        ext_item.setFlags(ext_item.flags() | Qt.ItemFlag.ItemIsEditable)
                        ext_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                        actual_table.setItem(row, column_index, ext_item)
                    finally:
                        actual_table.blockSignals(signals_blocked)

    def on_gallery_cell_clicked(self, row, column):
        """Handle clicks on gallery table cells for template editing and custom/ext column editing."""
        mw = self._main_window

        # Handle custom columns (14-17) and ext columns (18-21) with single-click editing
        if (GalleryTableWidget.COL_CUSTOM1 <= column <= GalleryTableWidget.COL_CUSTOM4) or \
           (GalleryTableWidget.COL_EXT1 <= column <= GalleryTableWidget.COL_EXT4):
            # Get the correct table and trigger edit mode
            table = getattr(mw.gallery_table, 'table', mw.gallery_table)
            if table:
                item = table.item(row, column)
                if item:
                    table.editItem(item)
            return

        # Handle clicks on template or image host columns
        if column not in (GalleryTableWidget.COL_TEMPLATE, GalleryTableWidget.COL_IMAGE_HOST):
            return

        # Get the table widget
        if hasattr(mw.gallery_table, 'table'):
            table = mw.gallery_table.table
        else:
            table = mw.gallery_table

        # Get gallery path the same way as context menu - from name column UserRole data
        name_item = table.item(row, GalleryTableWidget.COL_NAME)
        if not name_item:
            log(f"No item found at row {row}, column {GalleryTableWidget.COL_NAME}", category="ui", level="trace")
            return

        gallery_path = name_item.data(Qt.ItemDataRole.UserRole)
        if not gallery_path:
            log(f"No UserRole data in gallery name column", category="ui", level="trace")
            return

        from PyQt6.QtWidgets import QInputDialog

        if column == GalleryTableWidget.COL_TEMPLATE:
            # Get current template
            template_item = table.item(row, GalleryTableWidget.COL_TEMPLATE)
            current_template = template_item.text() if template_item else "default"

            from src.utils.templates import load_templates

            try:
                templates = load_templates()
                template_list = list(templates.keys())

                new_template, ok = QInputDialog.getItem(
                    mw,
                    "Select Template",
                    "Choose template for gallery:",
                    template_list,
                    template_list.index(current_template) if current_template in template_list else 0,
                    False
                )

                if ok and new_template != current_template:
                    self.update_gallery_template(row, gallery_path, new_template, None)

            except Exception as e:
                log(f"ERROR: Exception loading templates: {e}", category="ui", level="error")

        elif column == GalleryTableWidget.COL_IMAGE_HOST:
            try:
                from src.core.image_host_config import get_image_host_config_manager
                enabled = get_image_host_config_manager().get_enabled_hosts()
                if len(enabled) < 2:
                    return

                host_names = [config.name for config in enabled.values()]
                host_ids = list(enabled.keys())

                # Get current host
                host_item = table.item(row, GalleryTableWidget.COL_IMAGE_HOST)
                current_name = host_item.text() if host_item else ""
                current_idx = host_names.index(current_name) if current_name in host_names else 0

                new_name, ok = QInputDialog.getItem(
                    mw,
                    "Select Image Host",
                    "Choose image host for gallery:",
                    host_names,
                    current_idx,
                    False
                )

                if ok and new_name != current_name:
                    new_host_id = host_ids[host_names.index(new_name)]
                    self.set_image_host_for_galleries([gallery_path], new_host_id)

            except Exception as e:
                log(f"Exception in image host selection: {e}", category="ui", level="error")

    def update_gallery_template(self, row, gallery_path, new_template, combo_widget):
        """Update template for a gallery and regenerate BBCode if needed."""
        mw = self._main_window
        try:
            # Get table reference
            if hasattr(mw.gallery_table, 'table'):
                table = mw.gallery_table.table
            else:
                table = mw.gallery_table

            # Update database
            success = mw.queue_manager.store.update_item_template(gallery_path, new_template)

            # Update in-memory item
            with QMutexLocker(mw.queue_manager.mutex):
                if gallery_path in mw.queue_manager.items:
                    mw.queue_manager.items[gallery_path].template_name = new_template
                    mw.queue_manager._inc_version()

            # Update the table cell display
            template_item = table.item(row, GalleryTableWidget.COL_TEMPLATE)
            if template_item:
                template_item.setText(new_template)
            else:
                log(f"No template item found at row {row}, column {GalleryTableWidget.COL_TEMPLATE}", category="ui", level="debug")

            log(f"Template updated", category="ui", level="info")

            # Get the actual gallery item to check real status
            gallery_item = mw.queue_manager.get_item(gallery_path)
            if not gallery_item:
                log(f"Could not get gallery item from queue manager", category="ui", level="trace")
                status = ""
            else:
                status = gallery_item.status

            log(f"Gallery status: '{status}'", category="ui", level="trace")

            if status == "completed":
                log(f"Gallery is completed, attempting BBCode regeneration", level="trace", category="fileio")
                # Try to regenerate BBCode from JSON artifact
                try:
                    mw.artifact_handler.regenerate_gallery_bbcode(gallery_path, new_template)
                    log(f"Template changed to '{new_template}' and BBCode regenerated for {os.path.basename(gallery_path)}", level="info", category="fileio")
                except Exception as e:
                    log(
                        f"WARNING: Template changed to '{new_template}'"
                        f" for {os.path.basename(gallery_path)},"
                        f" but BBCode regeneration failed: {e}",
                        category="fileio", level="warning",
                    )
            else:
                log(f"Gallery not completed, skipping BBCode regeneration", category="fileio", level="debug")

            # Remove combo box and update display
            table.removeCellWidget(row, GalleryTableWidget.COL_TEMPLATE)
            template_item = table.item(row, GalleryTableWidget.COL_TEMPLATE)
            if template_item:
                template_item.setText(new_template)

            # Force table refresh to ensure data is updated
            # Note: refresh_gallery_display doesn't exist, removing this call

        except Exception as e:
            log(f"ERROR: Exception updating gallery template: {e}", category="fileio", level="error")
            # Remove combo box on error
            try:
                table = mw.gallery_table.table
                table.removeCellWidget(row, GalleryTableWidget.COL_TEMPLATE)
            except (AttributeError, RuntimeError):
                pass

    def set_image_host_for_galleries(self, gallery_paths: list, host_id: str):
        """Update image host for multiple galleries (context menu or click-to-change)."""
        mw = self._main_window
        if not gallery_paths or not host_id:
            return

        from src.core.image_host_config import get_image_host_config_manager

        updated_count = 0
        for gallery_path in gallery_paths:
            try:
                # Only change galleries that haven't started uploading
                gallery_item = mw.queue_manager.get_item(gallery_path)
                if gallery_item and gallery_item.status in ("uploading", "completed"):
                    continue

                success = mw.queue_manager.store.update_item_image_host(gallery_path, host_id)
                if success:
                    updated_count += 1
                    with QMutexLocker(mw.queue_manager.mutex):
                        if gallery_path in mw.queue_manager.items:
                            mw.queue_manager.items[gallery_path].image_host_id = host_id
                            mw.queue_manager._inc_version()
            except Exception as e:
                log(f"Error updating image host for {gallery_path}: {e}", level="error", category="ui")

        # Update table display
        if updated_count > 0:
            table = getattr(mw.gallery_table, 'table', mw.gallery_table)
            if table:
                for row_idx in range(table.rowCount()):
                    name_item = table.item(row_idx, GalleryTableWidget.COL_NAME)
                    if name_item and name_item.data(Qt.ItemDataRole.UserRole) in gallery_paths:
                        host_cell = table.item(row_idx, GalleryTableWidget.COL_IMAGE_HOST)
                        if host_cell:
                            from src.core.host_registry import get_display_name
                            host_cell.setText(get_display_name(host_id))

            from src.utils.format_utils import timestamp
            config_mgr = get_image_host_config_manager()
            host_cfg = config_mgr.get_host(host_id)
            host_display = host_cfg.name if host_cfg else host_id
            galleries_word = "gallery" if updated_count == 1 else "galleries"
            mw.add_log_message(f"{timestamp()} Image host changed to '{host_display}' for {updated_count} {galleries_word}")

    def _on_table_item_changed(self, item):
        """Handle table item changes to persist custom columns"""
        mw = self._main_window
        try:
            # Prevent recursion - use a simple flag
            if hasattr(mw, '_in_item_changed_handler') and mw._in_item_changed_handler:
                return

            mw._in_item_changed_handler = True
            try:
                # Handle custom columns (14-17) and ext columns (18-21)
                column = item.column()
                is_custom = GalleryTableWidget.COL_CUSTOM1 <= column <= GalleryTableWidget.COL_CUSTOM4
                is_ext = GalleryTableWidget.COL_EXT1 <= column <= GalleryTableWidget.COL_EXT4

                if not (is_custom or is_ext):
                    return

                # Get the actual table that contains this item (important for tabbed galleries!)
                table = item.tableWidget()
                if not table:
                    log(f"WARNING: Item has no parent table widget, skipping", level="debug", category="ui")
                    return

                # Skip if table signals are blocked (indicates programmatic update)
                if table.signalsBlocked():
                    return

                # Get the gallery path from the name column (UserRole data)
                row = item.row()
                name_item = table.item(row, GalleryTableWidget.COL_NAME)
                if not name_item:
                    return

                path = name_item.data(Qt.ItemDataRole.UserRole)
                if not path:
                    return

                # Map column to field name
                field_names = {
                    GalleryTableWidget.COL_CUSTOM1: 'custom1',
                    GalleryTableWidget.COL_CUSTOM2: 'custom2',
                    GalleryTableWidget.COL_CUSTOM3: 'custom3',
                    GalleryTableWidget.COL_CUSTOM4: 'custom4',
                    GalleryTableWidget.COL_EXT1: 'ext1',
                    GalleryTableWidget.COL_EXT2: 'ext2',
                    GalleryTableWidget.COL_EXT3: 'ext3',
                    GalleryTableWidget.COL_EXT4: 'ext4',
                }
                field_name = field_names.get(column)
                if not field_name:
                    return

                # Get the new value and update the database
                new_value = item.text() or ''
                field_type = "ext" if is_ext else "custom"
                log(f"{field_type.capitalize()} field changed: {field_name}={new_value} for {os.path.basename(path)}", level="trace", category="ui")

                if mw.queue_manager:
                    # Block signals while updating to prevent cascade
                    signals_blocked = table.signalsBlocked()
                    table.blockSignals(True)
                    try:
                        # Update in-memory item
                        with QMutexLocker(mw.queue_manager.mutex):
                            if path in mw.queue_manager.items:
                                item_obj = mw.queue_manager.items[path]
                                setattr(item_obj, field_name, new_value)

                        # Save to database (outside mutex to avoid deadlock)
                        mw.queue_manager.store.update_item_custom_field(path, field_name, new_value)

                        # Increment version
                        with QMutexLocker(mw.queue_manager.mutex):
                            mw.queue_manager._inc_version()
                    finally:
                        table.blockSignals(signals_blocked)
            finally:
                mw._in_item_changed_handler = False

        except Exception as e:
            log(f"ERROR: Exception handling table item change: {e}", category="ui", level="error")
            import traceback
            traceback.print_exc()
