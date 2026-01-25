#!/usr/bin/env python3
"""Artifact handling for gallery completion processing and BBCode regeneration.

This module provides classes for managing gallery artifacts (BBCode, JSON, HTML files)
after upload completion and for regenerating BBCode when templates change.

Classes:
    CompletionWorker: Background thread for post-upload artifact processing
    ArtifactHandler: Manager for BBCode regeneration and artifact operations

Thread Safety:
    CompletionWorker runs in a separate QThread to avoid blocking the GUI.
    Uses Queue for thread-safe task submission from main thread.
"""

import os
import json
import queue
from queue import Queue
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import QMessageBox

from src.utils.logger import log
from src.utils.format_utils import format_binary_size

if TYPE_CHECKING:
    from src.gui.main_window import BBDropGUI


class CompletionWorker(QThread):
    """Background worker thread for post-upload gallery processing.

    Handles time-intensive tasks after gallery upload completes to avoid blocking
    the main GUI thread. Processes items from a queue sequentially.

    Tasks Performed:
        - BBCode file generation from templates
        - Gallery artifact saving (HTML, JSON, BBCode files)
        - Unnamed gallery tracking for auto-rename feature
        - Central storage coordination

    Signals:
        completion_processed(str): Emitted when processing finishes (gallery path)
        log_message(str): Emitted to send log messages to main thread

    Thread Safety:
        Uses Queue.Queue for thread-safe task submission from main thread.
        All heavy I/O and file operations run in this background thread.

    Example:
        >>> worker = CompletionWorker(parent=self)
        >>> worker.completion_processed.connect(self.on_completion_done)
        >>> worker.start()
        >>> worker.process_completion(path, results, gui_parent)
    """

    # Signals
    completion_processed = pyqtSignal(str)  # path - signals when completion processing is done
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.completion_queue = Queue()
        self.running = True

    def stop(self):
        self.running = False
        self.completion_queue.put(None)  # Signal to exit

    def process_completion(self, path: str, results: dict, gui_parent):
        """Queue a gallery completion for background processing.

        Args:
            path: Absolute filesystem path to the gallery folder
            results: Upload results dict containing:
                - gallery_id: IMX.to gallery ID
                - gallery_name: Gallery display name
                - images: List of uploaded image data with BBCode
                - failed_details: List of (filename, error) tuples
                - total_size: Total bytes uploaded
                - avg_width/height: Image dimension statistics
            gui_parent: Reference to BBDropGUI for queue_manager access

        Note:
            This method returns immediately; actual processing happens in background thread.
        """
        self.completion_queue.put((path, results, gui_parent))

    def run(self):
        """Process completions in background thread"""
        while self.running:
            try:
                item = self.completion_queue.get(timeout=1.0)
                if item is None:  # Exit signal
                    break

                path, results, gui_parent = item
                self._process_completion_background(path, results, gui_parent)
                self.completion_processed.emit(path)

            except queue.Empty:
                continue
            except Exception as e:
                log(f" ERROR: Completion processing error: {e}")

    def _process_completion_background(self, path: str, results: dict, gui_parent):
        """Do the heavy completion processing in background thread"""
        try:
            # Create gallery files with new naming format
            gallery_id = results.get('gallery_id', '')
            gallery_name = results.get('gallery_name', os.path.basename(path))

            if not gallery_id or not gallery_name:
                return

            # Only track for renaming if gallery is actually unnamed
            try:
                from bbdrop import save_unnamed_gallery, get_unnamed_galleries, check_gallery_renamed
                # Check if gallery is already renamed
                is_renamed = check_gallery_renamed(gallery_id)
                if not is_renamed:
                    # Check if already in unnamed tracking
                    existing_unnamed = get_unnamed_galleries()  # Returns Dict[str, str]
                    if gallery_id not in existing_unnamed:
                        save_unnamed_gallery(gallery_id, gallery_name)
                        log(f" [rename] Tracking gallery for auto-rename: {gallery_name}")
            except Exception as e:
                log(f"Exception in main_window: {e}", level="error", category="ui")
                raise

            # Use cached template functions to avoid blocking import
            generate_bbcode_from_template = getattr(self, '_generate_bbcode_from_template', lambda *args, **kwargs: "")

            # Prepare template data (include successes; failed shown separately)
            all_images_bbcode = ""
            for image_data in results.get('images', []):
                all_images_bbcode += image_data.get('bbcode', '') + "  "
            failed_details = results.get('failed_details', [])
            failed_summary = ""
            if failed_details:
                failed_summary_lines = [f"[b]Failed ({len(failed_details)}):[/b]"]
                for fname, reason in failed_details[:20]:
                    failed_summary_lines.append(f"- {fname}: {reason}")
                if len(failed_details) > 20:
                    failed_summary_lines.append(f"... and {len(failed_details) - 20} more")
                failed_summary = "\n" + "\n".join(failed_summary_lines)

            # Calculate statistics (always, not only when failures exist)
            queue_item = gui_parent.queue_manager.get_item(path)
            total_size = results.get('total_size', 0) or (queue_item.total_size if queue_item and getattr(queue_item, 'total_size', 0) else 0)
            try:
                format_binary_size = getattr(self, '_format_binary_size', lambda size, precision=2: f"{size} B" if size else "")
                folder_size = format_binary_size(total_size, precision=1)
            except Exception:
                folder_size = f"{total_size} B"
            avg_width = (queue_item.avg_width if queue_item and getattr(queue_item, 'avg_width', 0) else 0) or results.get('avg_width', 0)
            avg_height = (queue_item.avg_height if queue_item and getattr(queue_item, 'avg_height', 0) else 0) or results.get('avg_height', 0)
            max_width = (queue_item.max_width if queue_item and getattr(queue_item, 'max_width', 0) else 0) or results.get('max_width', 0)
            max_height = (queue_item.max_height if queue_item and getattr(queue_item, 'max_height', 0) else 0) or results.get('max_height', 0)
            min_width = (queue_item.min_width if queue_item and getattr(queue_item, 'min_width', 0) else 0) or results.get('min_width', 0)
            min_height = (queue_item.min_height if queue_item and getattr(queue_item, 'min_height', 0) else 0) or results.get('min_height', 0)

            # Get most common extension from uploaded images
            extensions = []
            for image_data in results.get('images', []):
                if 'image_url' in image_data:
                    url = image_data['image_url']
                    if '.' in url:
                        ext = url.split('.')[-1].upper()
                        if ext in ['JPG', 'PNG', 'GIF', 'BMP', 'WEBP']:
                            extensions.append(ext)
            extension = max(set(extensions), key=extensions.count) if extensions else "JPG"

            # Get template name and custom fields from the item
            item = gui_parent.queue_manager.get_item(path)
            template_name = item.template_name if item else "default"

            # Prepare custom fields dict
            custom_fields = {
                'custom1': item.custom1 if item else '',
                'custom2': item.custom2 if item else '',
                'custom3': item.custom3 if item else '',
                'custom4': item.custom4 if item else '',
                'ext1': item.ext1 if item else '',
                'ext2': item.ext2 if item else '',
                'ext3': item.ext3 if item else '',
                'ext4': item.ext4 if item else ''
            }

            # Use centralized save_gallery_artifacts function
            try:
                from bbdrop import save_gallery_artifacts, load_user_defaults
                written = save_gallery_artifacts(
                    folder_path=path,
                    results={
                        **results,
                        'started_at': datetime.fromtimestamp(gui_parent.queue_manager.items[path].start_time).strftime('%Y-%m-%d %H:%M:%S') if path in gui_parent.queue_manager.items and gui_parent.queue_manager.items[path].start_time else None,
                        'thumbnail_size': gui_parent.thumbnail_size_combo.currentIndex() + 1,
                        'thumbnail_format': gui_parent.thumbnail_format_combo.currentIndex() + 1,
                        'parallel_batch_size': load_user_defaults().get('parallel_batch_size', 4),
                    },
                    template_name=template_name,
                    custom_fields=custom_fields
                )
                try:
                    parts = []
                    if written.get('central'):
                        parts.append(f"central: {os.path.dirname(list(written['central'].values())[0])}")
                    if written.get('uploaded'):
                        parts.append(f"folder: {os.path.dirname(list(written['uploaded'].values())[0])}")
                    if parts:
                        log(f" [fileio] INFO: Saved gallery files to {', '.join(parts)}", category="fileio", level="debug")
                except Exception as e:
                    log(f"Exception in main_window: {e}", level="error", category="ui")
                    raise
            except Exception as e:
                log(f" ERROR: Artifact save error: {e}")

        except Exception as e:
            log(f" ERROR: Background completion processing error: {e}")


class ArtifactHandler(QObject):
    """Manager for BBCode regeneration and artifact operations.

    This class provides methods for regenerating BBCode files for completed galleries,
    either individually or in batch. It handles loading gallery data from JSON artifacts
    and regenerating output files with updated templates.

    Attributes:
        _main_window: Reference to main GUI window for accessing queue_manager and settings

    Example:
        >>> handler = ArtifactHandler(main_window)
        >>> handler.regenerate_bbcode_for_gallery(gallery_path, force=True)
    """

    def __init__(self, main_window: 'BBDropGUI'):
        """Initialize the artifact handler.

        Args:
            main_window: Reference to BBDropGUI instance
        """
        super().__init__()
        self._main_window = main_window

    def regenerate_bbcode_for_gallery(self, gallery_path: str, force: bool = False):
        """Regenerate BBCode for a gallery using its current template.

        Args:
            gallery_path: Absolute path to the gallery folder
            force: If True, regenerate even if auto-regeneration is disabled
        """
        # Check if auto-regeneration is enabled (unless forced)
        if not force and not self.should_auto_regenerate_bbcode(gallery_path):
            return

        # Get the current template for this gallery
        item = self._main_window.queue_manager.get_item(gallery_path)
        if item and item.template_name:
            template_name = item.template_name
        else:
            # Fall back to default template
            template_name = "default"

        # Call the existing regeneration method
        self.regenerate_gallery_bbcode(gallery_path, template_name)

    def regenerate_bbcode_for_gallery_multi(self, paths):
        """Regenerate BBCode for multiple completed galleries using their current templates.

        Args:
            paths: List of gallery paths to regenerate
        """
        log(f"DEBUG: regenerate_bbcode_for_gallery_multi called with {len(paths)} paths", category="fileio", level="debug")

        # Find the main GUI window
        widget = self._main_window
        while widget and not hasattr(widget, 'queue_manager'):
            widget = widget.parent()
        if not widget:
            log(f"DEBUG: No widget with queue_manager found", category="fileio", level="debug")
            return

        success_count = 0
        error_count = 0

        for path in paths:
            try:
                log(f"DEBUG: Processing path: {path}", level="debug", category="fileio")
                item = widget.queue_manager.get_item(path)
                if not item:
                    log(f"DEBUG: No item found for path: {path}", category="fileio", level="debug")
                    continue

                if item.status != "completed":
                    log(f"DEBUG: Skipping non-completed item: {item.status}", category="fileio", level="debug")
                    continue

                # Get template for this gallery (same logic as single version)
                if item and item.template_name:
                    template_name = item.template_name
                else:
                    template_name = "default"

                # Call the existing regeneration method (force=True since this is explicit user action)
                self.regenerate_gallery_bbcode(path, template_name)
                success_count += 1
                log(f"DEBUG: Successfully regenerated BBCode for {path}", category="fileio", level="debug")

            except Exception as e:
                error_count += 1
                log(f"WARNING: Error regenerating BBCode for {path}: {e}", category="fileio", level="warning")

        # Show summary message
        if success_count > 0 or error_count > 0:
            if error_count == 0:
                QMessageBox.information(self._main_window, "Success", f"Regenerated BBCode for {success_count} galleries.")
            else:
                QMessageBox.warning(self._main_window, "Partial Failure", f"Regenerated {success_count}, failed {error_count}")
        else:
            QMessageBox.information(self._main_window, "No Action", "No completed galleries found to regenerate.")

    def regenerate_gallery_bbcode(self, gallery_path, new_template):
        """Regenerate BBCode for an uploaded gallery using its JSON artifact.

        Args:
            gallery_path: Absolute path to the gallery folder
            new_template: Name of the template to use for regeneration

        Raises:
            Exception: If gallery not found, no JSON artifact, or regeneration fails
        """
        from bbdrop import get_central_storage_path, build_gallery_filenames, save_gallery_artifacts
        import json
        import glob
        import os

        # Get gallery info
        item = self._main_window.queue_manager.get_item(gallery_path)
        if not item:
            raise Exception("Gallery not found in database")

        # Find JSON artifact file by gallery ID
        from src.utils.artifact_finder import find_gallery_json_by_id

        gallery_id = getattr(item, 'gallery_id', None)
        if not gallery_id:
            raise Exception("Gallery ID not found in database")

        json_path = find_gallery_json_by_id(gallery_id, gallery_path)
        if not json_path:
            raise Exception(f"No JSON artifact file found for gallery ID {gallery_id}")

        # Load JSON data
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        # Debug: Log the stats section from JSON to diagnose 0x0 dimension issues
        stats = json_data.get('stats', {})
        avg_width = stats.get('avg_width', 0)
        avg_height = stats.get('avg_height', 0)
        if avg_width == 0 or avg_height == 0:
            log(f"WARNING: Dimensions are 0 for gallery regeneration. "
                f"JSON path: {json_path}, stats section: {stats}", category="fileio")

        # Reuse existing save_gallery_artifacts function with the new template
        # It will handle BBCode generation, file saving, and JSON updates
        # Use current gallery name from database (which could be renamed), not from old JSON
        current_gallery_name = item.name if item.name else json_data['meta']['gallery_name']
        #print(f"DEBUG regenerate_gallery_bbcode: Using current_gallery_name='{current_gallery_name}' from database, old JSON had='{json_data['meta']['gallery_name']}'")
        results = {
            'gallery_id': json_data['meta']['gallery_id'],
            'gallery_name': current_gallery_name,
            'images': json_data.get('images', []),
            'total_size': stats.get('total_size', 0),
            'successful_count': stats.get('successful_count', 0),
            'failed_count': stats.get('failed_count', 0),
            'failed_details': [(img.get('filename', ''), 'Previous failure') for img in json_data.get('failures', [])],
            'avg_width': avg_width,
            'avg_height': avg_height,
            'max_width': stats.get('max_width', 0),
            'max_height': stats.get('max_height', 0),
            'min_width': stats.get('min_width', 0),
            'min_height': stats.get('min_height', 0)
        }

        # Prepare custom fields dict from the item
        custom_fields = {
            'custom1': getattr(item, 'custom1', ''),
            'custom2': getattr(item, 'custom2', ''),
            'custom3': getattr(item, 'custom3', ''),
            'custom4': getattr(item, 'custom4', ''),
            'ext1': getattr(item, 'ext1', ''),
            'ext2': getattr(item, 'ext2', ''),
            'ext3': getattr(item, 'ext3', ''),
            'ext4': getattr(item, 'ext4', '')
        }

        # Use existing save_gallery_artifacts function to regenerate with new template
        save_gallery_artifacts(
            folder_path=gallery_path,
            results=results,
            template_name=new_template,
            custom_fields=custom_fields
        )

    def should_auto_regenerate_bbcode(self, path: str) -> bool:
        """Check if BBCode should be auto-regenerated for a gallery.

        Args:
            path: Gallery path to check

        Returns:
            True if auto-regeneration is enabled and gallery is completed
        """
        # Check if auto-regeneration is enabled
        from bbdrop import load_user_defaults
        defaults = load_user_defaults()
        if not defaults.get('auto_regenerate_bbcode', True):
            return False

        # Check if gallery is completed
        item = self._main_window.queue_manager.get_item(path)
        if not item or item.status != "completed":
            return False

        return True

    def auto_regenerate_for_db_id(self, db_id: int):
        """Auto-regenerate artifacts for gallery by ID if setting enabled.

        Args:
            db_id: Database ID of the gallery
        """
        path = self._main_window._db_id_to_path.get(db_id)
        if path and self.should_auto_regenerate_bbcode(path):
            self.regenerate_bbcode_for_gallery(path, force=False)
