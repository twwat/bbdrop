#!/usr/bin/env python3
"""
Upload worker threads for bbdrop
Handles gallery uploads and completion tracking in background threads
"""

import os
import time
import threading
from typing import Optional, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QSettings

from bbdrop import (
    timestamp, load_user_defaults, rename_all_unnamed_with_session,
    save_gallery_artifacts, get_unnamed_galleries
)
from src.network.image_host_factory import create_image_host_client
from src.utils.logger import log
from src.storage.queue_manager import GalleryQueueItem
from src.core.engine import UploadEngine, AtomicCounter, ByteCountingCallback
from src.core.image_host_config import get_image_host_setting, get_image_host_config_manager, is_image_host_enabled, get_enabled_hosts
from src.processing.hooks_executor import execute_gallery_hooks

# Import RenameWorker at module level for testing
try:
    from src.processing.rename_worker import RenameWorker
except ImportError:
    RenameWorker = None  # type: ignore[misc,assignment]  # Will be handled gracefully in __init__

# Stub for generate_bbcode_from_results (for testing - doesn't exist in bbdrop)
# Tests will patch this, real code imports locally
generate_bbcode_from_results = None


class UploadWorker(QThread):
    """Worker thread for uploading galleries"""

    # Signals for communication with GUI
    progress_updated = pyqtSignal(str, int, int, int, str)  # path, completed, total, progress%, current_image
    gallery_started = pyqtSignal(str, int)  # path, total_images
    gallery_completed = pyqtSignal(str, dict)  # path, results
    gallery_failed = pyqtSignal(str, str)  # path, error_message
    gallery_exists = pyqtSignal(str, list)  # gallery_name, existing_files
    gallery_renamed = pyqtSignal(str)  # gallery_id
    ext_fields_updated = pyqtSignal(str, dict)  # path, ext_fields dict (for hook results)
    log_message = pyqtSignal(str)
    queue_stats = pyqtSignal(dict)  # aggregate status stats for GUI updates
    bandwidth_updated = pyqtSignal(float)  # Instantaneous KB/s from pycurl progress callbacks

    def __init__(self, queue_manager):
        """Initialize upload worker with queue manager"""
        super().__init__()
        self.queue_manager = queue_manager
        self.uploader = None
        self.running = True
        self.current_item = None
        self._soft_stop_requested_for = None
        self.auto_rename_enabled = True
        self._stats_last_emit = 0.0

        # Bandwidth tracking counters
        self.global_byte_counter = AtomicCounter()  # Persistent across ALL galleries (Speed box)
        self.current_gallery_counter: Optional[AtomicCounter] = None  # Per-gallery running average

        # Bandwidth calculation state - initialize to current counter to avoid initial spike
        self._bw_last_bytes = self.global_byte_counter.get()
        self._bw_last_time = time.time()
        self._bw_last_emit = 0.0

        # Initialize RenameWorker support
        self.rename_worker = None
        self._rename_worker_available = (RenameWorker is not None)


    def stop(self):
        """Stop the worker thread"""
        self.running = False
        # Cleanup RenameWorker
        if hasattr(self, 'rename_worker') and self.rename_worker:
            try:
                self.rename_worker.stop()
            except Exception as e:
                log(f"Error stopping RenameWorker: {e}", level="error", category="renaming")
        self.wait()

    def request_soft_stop_current(self):
        """Request to stop the current item after in-flight uploads finish"""
        if self.current_item:
            self._soft_stop_requested_for = self.current_item.path

    def run(self):
        """Main worker thread loop"""
        try:
            # Initialize uploader and perform initial login
            self._initialize_uploader()

            # Main processing loop
            while self.running:
                # Get next item from queue
                item = self.queue_manager.get_next_item()

                if item is None:
                    # No items to process, emit stats and wait
                    self._emit_queue_stats()
                    time.sleep(0.1)
                    continue

                # Process items based on status
                if item.status == "queued":
                    self.current_item = item
                    self.upload_gallery(item)
                elif item.status == "paused":
                    # Skip paused items
                    self._emit_queue_stats()
                    time.sleep(0.1)
                else:
                    # Unexpected status, skip
                    self._emit_queue_stats()
                    time.sleep(0.1)

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            log(f"CRITICAL: Worker thread crashed: {error_trace}", level="critical", category="uploads")
            # Also print directly to ensure it's visible
            print(f"\n{'='*70}\nWORKER THREAD CRASH:\n{error_trace}\n{'='*70}\n", flush=True)

    def _initialize_uploader(self, host_id: str = "imx"):
        """Initialize uploader with API-only mode and separate RenameWorker"""
        # Stop old RenameWorker before creating new one (prevent thread leak)
        if hasattr(self, 'rename_worker') and self.rename_worker is not None:
            try:
                self.rename_worker.stop()
                log("Stopped previous RenameWorker before host switch", level="debug", category="renaming")
            except Exception as e:
                log(f"Error stopping previous RenameWorker: {e}", level="warning", category="renaming")
            self.rename_worker = None

        # Initialize uploader using factory pattern for multi-host support
        self.uploader = create_image_host_client(host_id)
        if hasattr(self.uploader, 'worker_thread'):
            self.uploader.worker_thread = self
        self._current_host_id = host_id

        # RenameWorker is IMX-specific — only create for IMX
        if host_id == 'imx' and self._rename_worker_available and RenameWorker is not None:
            try:
                self.rename_worker = RenameWorker()
                log("RenameWorker initialized", category="renaming", level="debug")
            except Exception as e:
                log(f"Failed to initialize RenameWorker: {e}", level="error", category="renaming")
                self.rename_worker = None
        else:
            self.rename_worker = None

        log(f"Uploader initialized for host '{host_id}'", level="debug", category="auth")


    def upload_gallery(self, item: GalleryQueueItem):
        """Upload a single gallery"""
        # Start bandwidth polling thread for real-time updates
        import threading
        stop_polling = threading.Event()
        observed_peak_kbps = 0.0  # Track peak speed during this upload

        def poll_bandwidth():
            """Background thread that polls byte counter and emits bandwidth updates"""
            nonlocal observed_peak_kbps
            poll_last_bytes = self.global_byte_counter.get()  # Start from current cumulative value
            poll_last_time = time.time()

            while not stop_polling.is_set():
                time.sleep(0.2)  # Poll every 200ms

                try:
                    current_bytes = self.global_byte_counter.get()
                    current_time = time.time()

                    if current_bytes > poll_last_bytes:
                        time_diff = current_time - poll_last_time
                        if time_diff > 0:
                            instant_kbps = ((current_bytes - poll_last_bytes) / time_diff) / 1024.0
                            self.bandwidth_updated.emit(instant_kbps)
                            # Track peak speed
                            if instant_kbps > observed_peak_kbps:
                                observed_peak_kbps = instant_kbps
                            poll_last_bytes = current_bytes
                            poll_last_time = current_time
                except Exception:
                    pass

        polling_thread = threading.Thread(target=poll_bandwidth, daemon=True, name="BandwidthPoller")
        polling_thread.start()

        try:
            # Determine which host to use for this item
            host_id = getattr(item, 'image_host_id', None)
            if not host_id:
                # No host set — use first enabled host
                enabled = get_enabled_hosts()
                host_id = next(iter(enabled)) if enabled else None
                if host_id:
                    item.image_host_id = host_id
                    log(f"No image host set, using '{host_id}'",
                        level="info", category="uploads")

            if not host_id:
                error_msg = "No image hosts are enabled. Enable one in Settings > Image Hosts."
                item.error_message = error_msg
                self.queue_manager.mark_upload_failed(item.path, error_msg)
                self.gallery_failed.emit(item.path, error_msg)
                return

            # If the item's host is disabled, fall back to any enabled host
            if not is_image_host_enabled(host_id):
                enabled = get_enabled_hosts()
                if enabled:
                    fallback_id = next(iter(enabled))
                    log(f"Host '{host_id}' is disabled, using '{fallback_id}' instead",
                        level="info", category="uploads")
                    host_id = fallback_id
                    item.image_host_id = fallback_id
                else:
                    error_msg = "No image hosts are enabled. Enable one in Settings > Image Hosts."
                    item.error_message = error_msg
                    self.queue_manager.mark_upload_failed(item.path, error_msg)
                    self.gallery_failed.emit(item.path, error_msg)
                    return

            if not hasattr(self, '_current_host_id') or self._current_host_id != host_id:
                self._initialize_uploader(host_id)

            # Check for soft-stop request BEFORE clearing
            soft_stop_requested = getattr(self, '_soft_stop_requested_for', None) == item.path

            # Clear previous soft-stop request
            self._soft_stop_requested_for = None

            # Create per-gallery counter for running average
            self.current_gallery_counter = AtomicCounter()

            log(f"Starting upload: {item.name or os.path.basename(item.path)}", category="uploads", level="info")

            # Update status to uploading
            self.queue_manager.update_item_status(item.path, "uploading")
            item.start_time = time.time()

            # Execute "started" hook in background
            def run_started_hook():
                try:
                    ext_fields = execute_gallery_hooks(
                        event_type='started',
                        gallery_path=item.path,
                        gallery_name=item.name,
                        tab_name=item.tab_name,
                        image_count=item.total_images or 0,
                        cover_path=item.cover_source_path or '',
                    )
                    # Update ext fields if hook returned any
                    if ext_fields:
                        # Handle cover from hook output before generic field update
                        self._apply_cover_from_hook(item, ext_fields)
                        # Set ext1-4 fields on item (skip cover keys)
                        for key, value in ext_fields.items():
                            if key not in ('cover_path', 'cover_url'):
                                setattr(item, key, value)
                        self.queue_manager._schedule_debounced_save([item.path])
                        log(f"Updated ext fields from started hook: {ext_fields}", level="info", category="hooks")
                        # Emit signal to update GUI
                        self.ext_fields_updated.emit(item.path, ext_fields)
                except Exception as e:
                    log(f"Error executing started hook: {e}", level="error", category="hooks")

            threading.Thread(target=run_started_hook, daemon=True).start()

            # Emit start signal
            self.gallery_started.emit(item.path, item.total_images or 0)
            self._emit_queue_stats(force=True)

            # Check for early soft stop request (using saved value from before clearing)
            if soft_stop_requested:
                self.queue_manager.update_item_status(item.path, "incomplete")
                return

            # Get per-host upload settings (3-tier fallback: INI -> JSON -> hardcoded)
            thumbnail_size = get_image_host_setting(host_id, 'thumbnail_size', 'int')
            thumbnail_format = get_image_host_setting(host_id, 'thumbnail_format', 'int')
            max_retries = get_image_host_setting(host_id, 'max_retries', 'int')
            parallel_batch_size = get_image_host_setting(host_id, 'parallel_batch_size', 'int')
            # Pass the item directly for precalculated dimensions (engine uses getattr on it)
            if item.scan_complete and (item.avg_width or item.avg_height):
                log(f"Using precalculated dimensions for {item.name}: {item.avg_width}x{item.avg_height}", level="debug", category="uploads")

            # Run upload engine directly with any ImageHostClient (host-agnostic)
            results = self._run_upload_engine(
                item, thumbnail_size, thumbnail_format,
                max_retries, parallel_batch_size,
            )

            # Handle paused state
            if item.status == "paused":
                log(f"Upload paused: {item.name}", level="info", category="uploads")
                return

            # Store observed peak speed on item for metrics recording
            item.observed_peak_kbps = observed_peak_kbps

            # Process results
            self._process_upload_results(item, results)

        except FileNotFoundError as e:
            error_msg = f"Gallery folder not found: {item.path}\nThe folder may have been moved or deleted."
            log(error_msg, level="error", category="uploads")
            item.error_message = error_msg
            self.queue_manager.mark_upload_failed(item.path, error_msg)
            self.gallery_failed.emit(item.path, error_msg)
        except Exception as e:
            import traceback
            error_msg = str(e)
            error_trace = traceback.format_exc()
            log(f"Error uploading {item.name}: {error_msg}\n{error_trace}", level="error", category="uploads")

            # Record metrics for failed upload with dynamic host name
            from src.utils.metrics_store import get_metrics_store
            metrics_store = get_metrics_store()
            if metrics_store and item.start_time:
                _cfg = get_image_host_config_manager().get_host(host_id)
                _host_name = _cfg.name if _cfg else host_id
                transfer_time = time.time() - item.start_time
                metrics_store.record_transfer(
                    host_name=_host_name,
                    bytes_uploaded=0,
                    transfer_time=transfer_time,
                    success=False,
                    observed_peak_kbps=None
                )

            item.error_message = error_msg
            self.queue_manager.mark_upload_failed(item.path, error_msg)
            self.gallery_failed.emit(item.path, error_msg)
        finally:
            # Stop bandwidth polling thread
            stop_polling.set()
            polling_thread.join(timeout=0.5)

            # Clear gallery counter
            self.current_gallery_counter = None

    def _apply_cover_from_hook(self, item: GalleryQueueItem, ext_fields: Dict[str, str]) -> None:
        """Set cover_source_path from hook output if no cover is already set.

        Handles two keys from the hook JSON result:
        - ``cover_path``: local file path used directly
        - ``cover_url``: remote URL downloaded to a temp file

        Manual / auto-detected covers take priority -- an existing
        ``cover_source_path`` is never overwritten.
        """
        if item.cover_source_path:
            return

        cover_path = ext_fields.get('cover_path')
        if cover_path:
            if os.path.isfile(cover_path):
                item.cover_source_path = cover_path
                log(f"Cover set from hook: {cover_path}", level="info", category="cover")
            else:
                log(f"Cover path from hook does not exist: {cover_path}", level="warning", category="cover")
            return

        cover_url = ext_fields.get('cover_url')
        if cover_url:
            import tempfile
            import requests
            try:
                resp = requests.get(cover_url, timeout=30)
                resp.raise_for_status()
                # Derive file extension from URL (strip query string first)
                suffix = os.path.splitext(cover_url.split('?')[0])[1] or '.jpg'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix='cover_') as tmp:
                    tmp.write(resp.content)
                    item.cover_source_path = tmp.name
                log(f"Downloaded cover from hook URL: {cover_url}", level="info", category="cover")
            except Exception as e:
                log(f"Failed to download cover from hook URL: {e}", level="warning", category="cover")

    def _upload_cover(self, item: GalleryQueueItem, gallery_id: str = ""):
        """Upload cover photo if configured. Returns result dict or None.

        Cover failure never blocks gallery completion.
        """
        if not item.cover_source_path:
            return None

        try:
            settings = QSettings("BBDropUploader", "BBDropGUI")

            cover_host_id = (item.cover_host_id
                             or settings.value('cover/host_id', '', type=str)
                             or item.image_host_id or "imx")
            thumbnail_format = settings.value('cover/thumbnail_format', 2, type=int)
            cover_gallery = settings.value('cover/gallery', '', type=str)

            # Determine gallery attachment
            if item.image_host_id == cover_host_id:
                cover_gallery_id = gallery_id
            else:
                cover_gallery_id = cover_gallery

            # Route to appropriate upload method
            if cover_host_id == "imx":
                if not self.rename_worker or not getattr(self.rename_worker, 'login_successful', False):
                    log("Cover upload skipped: no authenticated IMX session", level="debug", category="cover")
                    return None
                result = self.rename_worker.upload_cover(
                    image_path=item.cover_source_path,
                    gallery_id=cover_gallery_id,
                    thumbnail_format=thumbnail_format,
                )
            else:
                cover_client = create_image_host_client(cover_host_id)
                raw_result = cover_client.upload_image(item.cover_source_path)
                result = cover_client.normalize_response(raw_result) if raw_result else None

            if result:
                item.cover_result = result
                log(f"Cover photo uploaded for {item.name}", level="info", category="cover")
            else:
                log(f"Cover photo upload failed for {item.name}", level="warning", category="cover")

            return result

        except Exception as e:
            log(f"Cover upload error for {item.name}: {e}", level="error", category="cover")
            return None

    def _process_upload_results(self, item: GalleryQueueItem, results: Optional[Dict[str, Any]]):
        """Process upload results and update item status"""
        if not results:
            # Handle failed upload
            if self._soft_stop_requested_for == item.path:
                self.queue_manager.update_item_status(item.path, "incomplete")
                item.status = "incomplete"
                log(f"Marked incomplete: {item.name}", level="info", category="uploads")
            else:
                self.queue_manager.mark_upload_failed(item.path, "Upload failed")
                self.gallery_failed.emit(item.path, "Upload failed")

            self._emit_queue_stats(force=True)
            return

        # Update item with results
        item.end_time = time.time()
        item.gallery_url = results.get('gallery_url', '')
        item.gallery_id = results.get('gallery_id', '')

        # Record metrics for successful upload with dynamic host name
        from src.utils.metrics_store import get_metrics_store
        metrics_store = get_metrics_store()
        if metrics_store and item.start_time:
            _host_id = getattr(item, 'image_host_id', 'imx') or 'imx'
            _cfg = get_image_host_config_manager().get_host(_host_id)
            _host_name = _cfg.name if _cfg else _host_id
            transfer_time = item.end_time - item.start_time
            metrics_store.record_transfer(
                host_name=_host_name,
                bytes_uploaded=item.uploaded_bytes or 0,
                transfer_time=transfer_time,
                success=True,
                observed_peak_kbps=getattr(item, 'observed_peak_kbps', None)
            )

        # Check for incomplete upload due to soft stop
        if (self._soft_stop_requested_for == item.path and
            results.get('successful_count', 0) < (item.total_images or 0)):
            self.queue_manager.update_item_status(item.path, "incomplete")
            item.status = "incomplete"
            log(f"Marked incomplete: {item.name}", level="info", category="uploads")
            return

        # Upload cover photo if configured (after gallery exists)
        cover_result = self._upload_cover(item, gallery_id=results.get('gallery_id', ''))

        # Save artifacts
        artifact_paths = self._save_artifacts_for_result(item, results)

        # Determine final status
        failed_count = results.get('failed_count', 0)
        if failed_count and results.get('successful_count', 0) > 0:
            # Partial failure - some images uploaded successfully but others failed
            failed_files = results.get('failed_details', [])
            self.queue_manager.mark_upload_failed(item.path, f"Partial upload failure: {failed_count} images failed", failed_files)
        else:
            # Complete success
            self.queue_manager.update_item_status(item.path, "completed")

            # Execute "completed" hook in background
            def run_completed_hook():
                try:
                    # Get artifact paths
                    json_path = ''
                    bbcode_path = ''
                    if artifact_paths:
                        # Try uploaded location first, then central
                        if 'uploaded' in artifact_paths:
                            json_path = artifact_paths['uploaded'].get('json', '')
                            bbcode_path = artifact_paths['uploaded'].get('bbcode', '')
                        elif 'central' in artifact_paths:
                            json_path = artifact_paths['central'].get('json', '')
                            bbcode_path = artifact_paths['central'].get('bbcode', '')

                    ext_fields = execute_gallery_hooks(
                        event_type='completed',
                        gallery_path=item.path,
                        gallery_name=item.name,
                        tab_name=item.tab_name,
                        image_count=results.get('successful_count', 0),
                        gallery_id=results.get('gallery_id', ''),
                        json_path=json_path,
                        bbcode_path=bbcode_path,
                        zip_path='',  # ZIP support not implemented yet
                        cover_path=item.cover_source_path or '',
                        cover_url=(item.cover_result or {}).get('image_url', ''),
                    )
                    # Update ext fields if hook returned any
                    if ext_fields:
                        # Handle cover from hook output before generic field update
                        self._apply_cover_from_hook(item, ext_fields)
                        # Set ext1-4 fields on item (skip cover keys)
                        for key, value in ext_fields.items():
                            if key not in ('cover_path', 'cover_url'):
                                setattr(item, key, value)
                        self.queue_manager._schedule_debounced_save([item.path])
                        log(f"Updated ext fields from completed hook: {ext_fields}", level="info", category="hooks")
                        # Emit signal to update GUI
                        self.ext_fields_updated.emit(item.path, ext_fields)
                except Exception as e:
                    log(f"Error executing completed hook: {e}", level="error", category="hooks")

            threading.Thread(target=run_completed_hook, daemon=True).start()

        # Notify GUI
        self.gallery_completed.emit(item.path, results)
        self._emit_queue_stats(force=True)

    def _save_artifacts_for_result(self, item: GalleryQueueItem, results: dict):
        """Save gallery artifacts (BBCode, JSON) in worker thread. Returns artifact paths dict."""
        try:
            # Build custom fields dict including ext1-4
            custom_fields = {
                'custom1': item.custom1,
                'custom2': item.custom2,
                'custom3': item.custom3,
                'custom4': item.custom4,
                'ext1': item.ext1,
                'ext2': item.ext2,
                'ext3': item.ext3,
                'ext4': item.ext4,
            }
            written = save_gallery_artifacts(
                folder_path=item.path,
                results=results,
                template_name=item.template_name or "default",
                custom_fields=custom_fields,
                cover_bbcode=(item.cover_result or {}).get('bbcode', ''),
            )
            # Artifact save successful, no need to log details here
            return written
        except Exception as e:
            log(f"Artifact save error: {e}", level="error", category="fileio")
            return {}

    def _emit_queue_stats(self, force: bool = False):
        """Emit queue statistics if needed"""
        now = time.time()
        if force or (now - self._stats_last_emit) > 1.0:
            try:
                stats = self.queue_manager.get_queue_stats()
                self.queue_stats.emit(stats)
                self._stats_last_emit = now
            except Exception:
                pass

    def _emit_current_bandwidth(self):
        """Calculate and emit current bandwidth from byte counter deltas"""
        try:
            current_time = time.time()
            current_bytes = self.global_byte_counter.get()

            # Throttle emissions to every 200ms minimum
            if (current_time - self._bw_last_emit) < 0.2:
                return

            # Calculate instantaneous bandwidth
            time_diff = current_time - self._bw_last_time
            if time_diff > 0:
                bytes_diff = current_bytes - self._bw_last_bytes
                if bytes_diff > 0:
                    instant_kbps = (bytes_diff / time_diff) / 1024.0
                    self.bandwidth_updated.emit(instant_kbps)
                    self._bw_last_emit = current_time

            # Update tracking
            self._bw_last_bytes = current_bytes
            self._bw_last_time = current_time
        except Exception:
            pass

    def _run_upload_engine(self, item: GalleryQueueItem, thumbnail_size: int,
                           thumbnail_format: int, max_retries: int,
                           parallel_batch_size: int) -> dict:
        """Run UploadEngine directly with any ImageHostClient.

        Replaces the previous uploader.upload_folder() call so that hosts
        without their own upload_folder (e.g. TurboImageHostClient) work
        through the same pipeline.
        """
        folder_path = item.path

        # Resume support
        already_uploaded = set(getattr(item, 'uploaded_files', set()))
        existing_gallery_id = (
            item.gallery_id
            if hasattr(item, 'gallery_id') and item.gallery_id
            else None
        )

        # Create engine
        engine = UploadEngine(
            self.uploader,
            self.rename_worker,
            global_byte_counter=self.global_byte_counter,
            gallery_byte_counter=self.current_gallery_counter,
            worker_thread=self,
        )

        # -- callbacks ---------------------------------------------------------
        def on_progress(completed: int, total: int, percent: int, current_image: str):
            self.progress_updated.emit(folder_path, completed, total, percent, current_image)
            try:
                self._emit_current_bandwidth()
            except Exception:
                pass

        def should_soft_stop() -> bool:
            if self.current_item and self.current_item.path == folder_path:
                return getattr(self, '_soft_stop_requested_for', None) == folder_path
            return False

        def on_image_uploaded(fname: str, data: dict, size_bytes: int):
            if self.current_item and self.current_item.path == folder_path:
                try:
                    self.current_item.uploaded_files.add(fname)
                    self.current_item.uploaded_images_data.append((fname, data))
                    self.current_item.uploaded_bytes += int(size_bytes or 0)
                except Exception as e:
                    log(f"Failed to track uploaded image {fname}: {e}",
                        level="error", category="uploads")

        # -- cover exclusion ---------------------------------------------------
        # When a cover file is set and "also upload as gallery image" is off,
        # exclude the cover from the normal gallery upload.
        exclude_cover = None
        if item.cover_source_path:
            settings = QSettings("BBDropUploader", "BBDropGUI")
            also_upload = settings.value(
                'cover/also_upload_as_gallery', False, type=bool)
            if not also_upload:
                exclude_cover = os.path.basename(item.cover_source_path)

        # -- run ---------------------------------------------------------------
        results = engine.run(
            folder_path=folder_path,
            gallery_name=item.name,
            thumbnail_size=thumbnail_size,
            thumbnail_format=thumbnail_format,
            max_retries=max_retries,
            parallel_batch_size=parallel_batch_size,
            template_name=item.template_name,
            already_uploaded=already_uploaded,
            existing_gallery_id=existing_gallery_id,
            precalculated_dimensions=item,
            exclude_cover_file=exclude_cover,
            on_progress=on_progress,
            should_soft_stop=should_soft_stop,
            on_image_uploaded=on_image_uploaded,
        )

        # Merge results from this run with previously uploaded images (resume)
        results = self._merge_resume_results(item, results, folder_path)
        return results

    def _merge_resume_results(self, item: GalleryQueueItem,
                              results: dict, folder_path: str) -> dict:
        """Combine images from the current run with previous partial runs.

        Needed for resume support: when a gallery was partially uploaded,
        paused, then resumed, this merges all images into the correct
        (Explorer-sorted) order.
        """
        import sys
        import ctypes
        import re
        from functools import cmp_to_key

        try:
            if not (self.current_item and self.current_item.path == folder_path):
                return results

            image_extensions = ('.jpg', '.jpeg', '.png', '.gif')

            def _natural_key(n: str):
                parts = re.split(r"(\d+)", n)
                out = []
                for p in parts:
                    out.append(int(p) if p.isdigit() else p.lower())
                return tuple(out)

            def _explorer_sort(names):
                if sys.platform != 'win32':
                    return sorted(names, key=_natural_key)
                try:
                    _cmp = ctypes.windll.shlwapi.StrCmpLogicalW
                    _cmp.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
                    _cmp.restype = ctypes.c_int
                    return sorted(names, key=cmp_to_key(lambda a, b: _cmp(a, b)))
                except Exception:
                    return sorted(names, key=_natural_key)

            all_image_files = _explorer_sort([
                f for f in os.listdir(folder_path)
                if f.lower().endswith(image_extensions)
                and os.path.isfile(os.path.join(folder_path, f))
            ])
            file_position = {fname: idx for idx, fname in enumerate(all_image_files)}

            # Collect enriched image data from accumulated uploads across runs
            combined_by_name = {}
            for fname, data in getattr(item, 'uploaded_images_data', []):
                try:
                    base, ext = os.path.splitext(fname)
                    fname_norm = base + ext.lower()
                except Exception:
                    fname_norm = fname
                enriched = dict(data)
                enriched.setdefault('original_filename', fname_norm)
                # Best-effort thumb_url via host-agnostic method
                image_url = enriched.get('image_url')
                if not enriched.get('thumb_url') and image_url:
                    try:
                        if hasattr(self.uploader, 'get_thumbnail_url'):
                            # Extract image ID from last URL path segment (host-agnostic)
                            url_path = image_url.rstrip('/').rsplit('/', 1)[-1]
                            img_id = os.path.splitext(url_path)[0] if url_path else ''
                            if img_id:
                                _, ext2 = os.path.splitext(fname_norm)
                                ext_use = (ext2.lower() or '.jpg') if ext2 else '.jpg'
                                enriched['thumb_url'] = self.uploader.get_thumbnail_url(
                                    img_id, ext_use)
                    except Exception:
                        pass
                try:
                    enriched.setdefault(
                        'size_bytes',
                        os.path.getsize(os.path.join(folder_path, fname)))
                except Exception:
                    enriched.setdefault('size_bytes', 0)
                combined_by_name[fname] = enriched

            ordered = sorted(combined_by_name.items(),
                             key=lambda kv: file_position.get(kv[0], 10**9))
            merged_images = [data for _fname, data in ordered]

            if merged_images:
                results = dict(results)
                results['images'] = merged_images
                results['successful_count'] = len(merged_images)
                try:
                    results['uploaded_size'] = sum(
                        int(img.get('size_bytes') or 0) for img in merged_images)
                except Exception:
                    pass
                results['total_images'] = len(all_image_files)
        except Exception:
            pass

        return results


class CompletionWorker(QThread):
    """Worker thread for handling gallery completion tasks"""

    # Signals for GUI communication
    bbcode_generated = pyqtSignal(str, str)  # path, bbcode
    log_message = pyqtSignal(str)
    artifact_written = pyqtSignal(str, dict)  # path, written_files

    def __init__(self):
        """Initialize completion worker"""
        super().__init__()
        self.queue = []
        self.running = True
        self._mutex = QMutex()

    def add_completion_task(self, item: GalleryQueueItem, results: dict):
        """Add a completion task to the queue"""
        try:
            self._mutex.lock()
            self.queue.append((item, results))
        finally:
            self._mutex.unlock()

    def stop(self):
        """Stop the worker thread"""
        self.running = False
        self.wait()

    def run(self):
        """Main worker loop for processing completion tasks"""
        while self.running:
            task = None

            # Get next task from queue
            try:
                self._mutex.lock()
                if self.queue:
                    task = self.queue.pop(0)
            finally:
                self._mutex.unlock()

            if task:
                item, results = task
                self._process_completion(item, results)
            else:
                time.sleep(0.1)

    def _process_completion(self, item: GalleryQueueItem, results: dict):
        """Process a single completion task"""
        try:
            # Use module-level function (allows test patching)
            # Will be generate_bbcode_from_results stub (patchable) or real import
            global generate_bbcode_from_results
            if generate_bbcode_from_results is None:
                # Not patched, use real function
                from bbdrop import generate_bbcode_from_template
                _gen_func = generate_bbcode_from_template
            else:
                # Patched by test or set to real function
                _gen_func = generate_bbcode_from_results

            # Generate BBCode (with correct argument order for real function)
            bbcode = _gen_func(
                item.template_name or "default",
                results
            )

            if bbcode:
                self.bbcode_generated.emit(item.path, bbcode)

            # Log artifact locations if available
            self._log_artifact_locations(results)

        except Exception as e:
            log(f"Completion processing error: {e}", level="error", category="uploads")

    def _log_artifact_locations(self, results: dict):
        """Log artifact save locations from results"""
        try:
            written = results.get('written_artifacts', {})
            if not written:
                return

            parts = []
            if written.get('central'):
                central_dir = os.path.dirname(list(written['central'].values())[0])
                parts.append(f"central: {central_dir}")
            if written.get('uploaded'):
                uploaded_dir = os.path.dirname(list(written['uploaded'].values())[0])
                parts.append(f"folder: {uploaded_dir}")

            if parts:
                log(f"Saved to {', '.join(parts)}", level="debug", category="fileio")

        except Exception:
            pass


class BandwidthTracker(QThread):
    """Background thread for tracking upload bandwidth"""

    bandwidth_updated = pyqtSignal(float)  # KB/s

    def __init__(self, upload_worker: Optional[UploadWorker] = None):
        """Initialize bandwidth tracker"""
        super().__init__()
        self.upload_worker = upload_worker
        self.running = True
        self._last_bytes = 0
        self._last_time = time.time()

    def stop(self):
        """Stop the bandwidth tracker"""
        self.running = False
        self.wait()

    def run(self):
        """Main loop for tracking bandwidth"""
        while self.running:
            try:
                if self.upload_worker and self.upload_worker.uploader:
                    current_bytes = getattr(self.upload_worker.uploader, 'total_bytes_uploaded', 0)
                    current_time = time.time()

                    if self._last_bytes > 0:
                        time_diff = current_time - self._last_time
                        bytes_diff = current_bytes - self._last_bytes

                        if time_diff > 0:
                            kb_per_sec = (bytes_diff / 1024) / time_diff
                            self.bandwidth_updated.emit(kb_per_sec)

                    self._last_bytes = current_bytes
                    self._last_time = current_time

                time.sleep(1.0)  # Update every second

            except Exception:
                pass
