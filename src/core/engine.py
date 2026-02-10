"""
Core upload engine shared by CLI and GUI.

This module centralizes the upload loop, retries, and statistics aggregation,
so both the CLI (`bbdrop.py`) and GUI (`bbdrop_gui.py`) can use the same logic
without duplication.
"""

from __future__ import annotations

import os, shutil
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import re
import sys
import threading
from functools import cmp_to_key
import ctypes
from typing import Callable, Iterable, Optional, Tuple, List, Dict, Any, Set

from src.utils.format_utils import format_binary_size, format_binary_rate
from src.utils.logger import log
from src.network.image_host_client import ImageHostClient


class AtomicCounter:
    """Thread-safe byte counter for tracking upload progress across multiple threads."""

    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def add(self, amount: int) -> None:
        """Add bytes to counter (thread-safe)."""
        with self._lock:
            self._value += amount

    def get(self) -> int:
        """Get current value (thread-safe)."""
        with self._lock:
            return self._value

    def reset(self) -> None:
        """Reset counter to zero (thread-safe)."""
        with self._lock:
            self._value = 0


class ByteCountingCallback:
    """Callback wrapper that tracks upload progress deltas and updates global counter."""

    def __init__(self, global_counter: Optional[AtomicCounter] = None,
                 gallery_counter: Optional[AtomicCounter] = None,
                 worker_thread: Optional[Any] = None):
        """Initialize with optional global counter.

        Args:
            global_counter: Tracks bytes across ALL galleries (used by Speed box)
            gallery_counter: Ignored (per-gallery tracking removed)
            worker_thread: Ignored (not needed)
        """
        self.global_counter = global_counter
        self.last_bytes = 0

    def __call__(self, bytes_read: int, total_size: int) -> None:
        """Called by pycurl during upload transmission."""
        delta = bytes_read - self.last_bytes
        if delta > 0 and self.global_counter:
            self.global_counter.add(delta)
            self.last_bytes = bytes_read


# Type aliases for callbacks
ProgressCallback = Callable[[int, int, int, str], None]
SoftStopCallback = Callable[[], bool]
ImageUploadedCallback = Callable[[str, Dict[str, Any], int], None]


class UploadEngine:
    """Shared engine for uploading a folder as a gallery.

    The engine expects an `uploader` object implementing the ImageHostClient ABC.
    """

    def __init__(self, uploader: ImageHostClient, rename_worker: Any = None,
                 global_byte_counter: Optional[AtomicCounter] = None,
                 gallery_byte_counter: Optional[AtomicCounter] = None,
                 worker_thread: Optional[Any] = None):
        """Initialize upload engine with counters.

        Args:
            uploader: Uploader instance
            rename_worker: Optional rename worker
            global_byte_counter: Persistent counter tracking ALL galleries
            gallery_byte_counter: Per-gallery counter (reset after each gallery)
            worker_thread: Optional worker thread reference for bandwidth emission
        """
        self.uploader = uploader
        self.rename_worker = rename_worker
        self.global_byte_counter = global_byte_counter or AtomicCounter()
        self.gallery_byte_counter = gallery_byte_counter  # Can be None
        self.worker_thread = worker_thread

    def _is_gallery_unnamed(self, gallery_id: str) -> bool:
        """Check if gallery is in the unnamed galleries list."""
        try:
            from bbdrop import get_unnamed_galleries  # type: ignore
            unnamed_galleries = get_unnamed_galleries()
            return gallery_id in unnamed_galleries
        except Exception as e:
            log(f"Failed to check gallery rename status: {e}", level="error", category="engine")
            return False

    def run(
        self,
        folder_path: str,
        gallery_name: Optional[str],
        thumbnail_size: int,
        thumbnail_format: int,
        max_retries: int,
        parallel_batch_size: int,
        template_name: str,
        content_type: str = "all",
        # Resume support from GUI; pass empty for CLI
        already_uploaded: Optional[Set[str]] = None,
        # Existing gallery ID for resume/append operations
        existing_gallery_id: Optional[str] = None,
        # Pre-calculated dimensions from scanning (optional, will calculate if not provided)
        precalculated_dimensions: Optional[Dict[str, float]] = None,
        # Cover photo exclusion: filename (basename) to skip from gallery upload
        exclude_cover_file: Optional[str] = None,
        # Callbacks (all optional)
        on_progress: Optional[ProgressCallback] = None,
        should_soft_stop: Optional[SoftStopCallback] = None,
        on_image_uploaded: Optional[ImageUploadedCallback] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        # Gather image files
        def _natural_sort_key(name: str):
            parts = re.split(r"(\d+)", name)
            key = []
            for p in parts:
                if p.isdigit():
                    try:
                        key.append(int(p))
                    except Exception as e:
                        log(f"Natural sort key parse failed: {e}", level="debug", category="engine")
                        key.append(p)
                else:
                    key.append(p.lower())
            return tuple(key)

        def _explorer_sort(names: List[str]) -> List[str]:
            """Windows Explorer (StrCmpLogicalW) ordering; fallback to natural sort on non-Windows."""
            if sys.platform != "win32":
                return sorted(names, key=_natural_sort_key)
            try:
                _cmp = ctypes.windll.shlwapi.StrCmpLogicalW
                _cmp.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
                _cmp.restype = ctypes.c_int
                return sorted(names, key=cmp_to_key(lambda a, b: _cmp(a, b)))
            except Exception as e:
                log(f"Explorer sort failed, using natural sort: {e}", level="debug", category="engine")
                return sorted(names, key=_natural_sort_key)
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif')
        all_image_files: List[str] = _explorer_sort([
            f for f in os.listdir(folder_path)
            if f.lower().endswith(image_extensions) and os.path.isfile(os.path.join(folder_path, f))
        ])

        # Exclude cover file from gallery upload (cover-only, not also-upload)
        if exclude_cover_file:
            all_image_files = [f for f in all_image_files if f != exclude_cover_file]

        if not all_image_files:
            raise ValueError(f"No image files found in {folder_path}")

        # Skip files over host's max file size limit
        host_config = getattr(self.uploader, 'config', None)
        max_mb = getattr(host_config, 'max_file_size_mb', None) if host_config else None
        if max_mb:
            max_bytes = max_mb * 1024 * 1024
            oversized = set()
            for f in all_image_files:
                try:
                    if os.path.getsize(os.path.join(folder_path, f)) > max_bytes:
                        oversized.add(f)
                        log(f"Skipping {f}: exceeds {max_mb}MB limit",
                            level="warning", category="uploads")
                except OSError:
                    pass
            if oversized:
                all_image_files = [f for f in all_image_files if f not in oversized]

        # Resume: exclude already-uploaded files
        already_uploaded = already_uploaded or set()
        image_files: List[str] = [f for f in all_image_files if f not in already_uploaded]

        original_total_images = len(all_image_files)

        # Fast pre-scan: only compute total size to avoid startup delay
        # Dimension sampling (if needed) is deferred until after uploads complete
        image_dimensions_map: Dict[str, Tuple[int, int]] = {}
        total_size = 0
        for f in all_image_files:
            fp = os.path.join(folder_path, f)
            try:
                total_size += os.path.getsize(fp)
            except OSError:
                pass

        # Determine gallery name
        if not gallery_name:
            gallery_name = os.path.basename(folder_path)
        original_name = gallery_name
        # Sanitize gallery name using the uploader's per-host rules
        if hasattr(self.uploader, 'sanitize_gallery_name'):
            gallery_name = self.uploader.sanitize_gallery_name(gallery_name)
            if original_name != gallery_name:
                log(f"Sanitized gallery name: '{original_name}' -> '{gallery_name}'", level="debug", category="uploads")

        # Use existing gallery or create new one
        gallery_id: Optional[str] = existing_gallery_id
        initial_completed = 0
        initial_uploaded_size = 0
        preseed_images: List[Dict[str, Any]] = []
        files_to_upload: List[str]

        if gallery_id:
            # Resume/append to existing gallery - no need to create new one
            log(f"Resuming/appending to existing gallery: {gallery_id}", level="info", category="uploads")
            files_to_upload = image_files
            # Set initial completed to the number of already-uploaded files for correct progress
            initial_completed = len(already_uploaded)
            # Keep uploaded_size at 0 since we're only tracking this session's uploads
            initial_uploaded_size = 0
        else:
            # Create new gallery via API by uploading the first image (faster, avoids web login delays)
            # CRITICAL: Clear pycurl API cookies to prevent gallery_id reuse from previous uploads
            # (Web session cookies are separate and should NOT be cleared here)
            if hasattr(self.uploader, 'clear_api_cookies'):
                self.uploader.clear_api_cookies()

            first_file = image_files[0]
            first_image_path = os.path.join(folder_path, first_file)
            log(f"Uploading first image to create gallery: {first_file}", level="info", category="uploads")
            first_upload_start = time.time()
            first_response = self.uploader.upload_image(
                first_image_path,
                create_gallery=True,
                thumbnail_size=thumbnail_size,
                thumbnail_format=thumbnail_format,
                progress_callback=ByteCountingCallback(self.global_byte_counter, self.gallery_byte_counter, self.worker_thread),
                content_type=content_type,
                gallery_name=gallery_name,
            )
            first_upload_duration = time.time() - first_upload_start
            if first_response.get('status') != 'success':
                raise Exception(f"Failed to create gallery: {first_response}")
            gallery_id = first_response['data'].get('gallery_id')
            preseed_images = [first_response['data']]
            # Log first image success with URL
            try:
                first_url = first_response['data'].get('image_url', '')
                log(f"Uploaded (in {first_upload_duration:.3f}s): {first_image_path}  ({first_url})", category="uploads:file")
            except Exception as e:
                log(f"Failed to log first image URL: {e}", level="warning", category="uploads")
            # First image uploaded - set counters and files_to_upload
            files_to_upload = image_files[1:]  # Remaining files after first
            initial_completed = 1
            try:
                initial_uploaded_size = os.path.getsize(first_image_path)
            except Exception as e:
                log(f"Failed to get first image size: {e}", level="warning", category="uploads")
                initial_uploaded_size = 0
            # Report the first image upload so GUI resume/merge includes it
            if on_image_uploaded:
                try:
                    on_image_uploaded(first_file, first_response['data'], initial_uploaded_size)
                except Exception as e:
                    log(f"on_image_uploaded callback failed: {e}", level="error", category="uploads")
        # Queue gallery rename for background processing to avoid blocking uploads
        if self.uploader.supports_gallery_rename() and gallery_name and gallery_id and (not existing_gallery_id or self._is_gallery_unnamed(gallery_id)):
            try:
                last_method = getattr(self.uploader, 'last_login_method', None)
            except Exception as e:
                log(f"Failed to get login method: {e}", level="debug", category="uploads")
                last_method = None

            if self.rename_worker:
                # Always try RenameWorker first (it will fallback internally if needed)
                log(f"Queuing gallery rename via RenameWorker (login method: {last_method})", level="debug", category="renaming")
                self.rename_worker.queue_rename(gallery_id, gallery_name)
            else:
                # No rename worker; queue for later auto-rename
                try:
                    from bbdrop import save_unnamed_gallery  # type: ignore
                    save_unnamed_gallery(gallery_id, gallery_name)
                    log(f"Queued gallery for auto-rename: '{gallery_name}' (no RenameWorker)", level="debug", category="renaming")
                except Exception as e:
                    log(f"Failed to queue gallery for auto-rename: {e}", level="error", category="renaming")
        # Emit an initial progress update
        if on_progress:
            percent_once = int((initial_completed / max(original_total_images, 1)) * 100)
            current_file = (first_file if 'first_file' in locals() else image_files[0] if image_files else "")
            on_progress(initial_completed, original_total_images, percent_once, current_file)

        # Use dynamic gallery URL from uploader (multi-host support)
        gallery_url = self.uploader.get_gallery_url(gallery_id, gallery_name=gallery_name)

        # Container for results
        results: Dict[str, Any] = {
            'gallery_url': gallery_url,
            'images': list(preseed_images),
        }

        def upload_single_image(image_file: str) -> Tuple[str, Optional[Dict[str, Any]], Optional[str], Optional[float], str]:
            image_path = os.path.join(folder_path, image_file)
            try:
                upload_start = time.time()

                response = self.uploader.upload_image(
                    image_path,
                    gallery_id=gallery_id,
                    thumbnail_size=thumbnail_size,
                    thumbnail_format=thumbnail_format,
                    progress_callback=ByteCountingCallback(self.global_byte_counter, self.gallery_byte_counter, self.worker_thread),
                    content_type=content_type,
                    gallery_name=gallery_name,
                )
                upload_duration = time.time() - upload_start
                if response.get('status') == 'success':
                    return image_file, response['data'], None, upload_duration, image_path
                return image_file, None, f"API error: {response}", None, image_path
            except Exception as e:
                return image_file, None, f"Upload error: {e}", None, image_path

        # Concurrency loop
        uploaded_images: List[Tuple[str, Dict[str, Any]]] = []
        failed_images: List[Tuple[str, str]] = []
        file_position = {fname: idx for idx, fname in enumerate(all_image_files)}

        def maybe_soft_stopping() -> bool:
            return bool(should_soft_stop and should_soft_stop())

        # Track concurrent uploads for visibility
        active_uploads = 0
        max_concurrent_seen = 0

        with ThreadPoolExecutor(max_workers=parallel_batch_size) as executor:
            remaining: List[str] = list(files_to_upload)
            futures_map: Dict[concurrent.futures.Future, str] = {}
            # Prime pool
            for _ in range(min(parallel_batch_size, len(remaining))):
                img = remaining.pop(0)
                futures_map[executor.submit(upload_single_image, img)] = img
                active_uploads += 1

            max_concurrent_seen = len(futures_map)
            #if on_log:
            #    on_log(f"[concurrency] Primed pool with {len(futures_map)} initial uploads")

            while futures_map:
                # Log current concurrency before waiting
                current_active = len(futures_map)
                if current_active > max_concurrent_seen:
                    max_concurrent_seen = current_active
                done, _ = concurrent.futures.wait(list(futures_map.keys()), return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in done:
                    img = futures_map.pop(fut)
                    active_uploads -= 1
                    image_file, image_data, error, upload_duration, image_path = fut.result()
                    if image_data:
                        uploaded_images.append((image_file, image_data))
                        # Per-image success log (categorized)
                        try:
                            img_url = image_data.get('image_url', '')
                            duration_str = f"{upload_duration:.3f}" if upload_duration is not None else "?.???"
                            url_suffix = f"  ({img_url})" if img_url else ""
                            log(f"Uploaded (in {duration_str}s): {image_path}{url_suffix}", category="uploads:file")
                        except Exception as e:
                            log(f"Failed to log upload URL: {e}", level="warning", category="uploads")
                        # Per-image callback for resume-aware consumers
                        if on_image_uploaded:
                            try:
                                size_bytes = os.path.getsize(os.path.join(folder_path, image_file))
                            except Exception as e:
                                log(f"Failed to get file size for {image_file}: {e}", level="warning", category="uploads")
                                size_bytes = 0
                            on_image_uploaded(image_file, image_data, size_bytes)
                    else:
                        failed_images.append((image_file, error or "unknown error"))
                        # Log the failure immediately with clear error indication
                        log(f"[uploads:file] ✗ Upload failed: {image_file} - {error or 'unknown error'}", level="warning", category="uploads:file")
                    # Progress
                    completed_count = initial_completed + len(uploaded_images)
                    if on_progress:
                        percent = int((completed_count / max(original_total_images, 1)) * 100)
                        on_progress(completed_count, original_total_images, percent, image_file)
                    # Queue next if not soft-stopping
                    if remaining and not maybe_soft_stopping():
                        nxt = remaining.pop(0)
                        futures_map[executor.submit(upload_single_image, nxt)] = nxt
                        active_uploads += 1

        # Retries
        retry_count = 0
        while failed_images and retry_count < max_retries and not maybe_soft_stopping():
            retry_count += 1
            retry_failed: List[Tuple[str, str]] = []
            log(f"[uploads] Retrying {len(failed_images)} failed uploads (attempt {retry_count}/{max_retries})", level="info", category="uploads")
            with ThreadPoolExecutor(max_workers=parallel_batch_size) as executor:
                remaining = [img for img, _ in failed_images]
                futures_map = {executor.submit(upload_single_image, img): img for img in remaining[:parallel_batch_size]}
                remaining = remaining[parallel_batch_size:]
                while futures_map:
                    done, _ = concurrent.futures.wait(list(futures_map.keys()), return_when=concurrent.futures.FIRST_COMPLETED)
                    for fut in done:
                        img = futures_map.pop(fut)
                        image_file, image_data, error, upload_duration, image_path = fut.result()
                        if image_data:
                            uploaded_images.append((image_file, image_data))
                            if on_image_uploaded:
                                try:
                                    size_bytes = os.path.getsize(os.path.join(folder_path, image_file))
                                except Exception as e:
                                    log(f"Failed to get file size for {image_file}: {e}", level="warning", category="uploads")
                                    size_bytes = 0
                                on_image_uploaded(image_file, image_data, size_bytes)
                            # Per-image success log (retry path)
                            try:
                                img_url = image_data.get('image_url', '')
                                duration_str = f"{upload_duration:.3f}" if upload_duration is not None else "?.???"
                                log(f"Uploaded (in {duration_str}s): {image_path}  ({img_url})", category="uploads:file")
                            except Exception as e:
                                log(f"Failed to log retry URL: {e}", level="warning", category="uploads")
                            log(f"[uploads] Retry successful: {image_file}", level="info", category="uploads")
                        else:
                            retry_failed.append((image_file, error or "unknown error"))
                            log(f"[uploads] ✗ Retry failed: {image_file} - {error or 'unknown error'}", level="warning", category="uploads")
                        completed_count = initial_completed + len(uploaded_images)
                        if on_progress:
                            percent = int((completed_count / max(original_total_images, 1)) * 100)
                            on_progress(completed_count, original_total_images, percent, image_file)
                        if remaining:
                            nxt = remaining.pop(0)
                            futures_map[executor.submit(upload_single_image, nxt)] = nxt
            failed_images = retry_failed

        # Log concurrency summary
        #if on_log:
        #    on_log(f"[concurrency] Upload complete - max concurrent uploads seen: {max_concurrent_seen}/{parallel_batch_size}")

        # Sort by original order
        uploaded_images.sort(key=lambda x: file_position.get(x[0], 10**9))
        for _, image_data in uploaded_images:
            results['images'].append(image_data)

        # Batch result fetch: hosts like Turbo upload per-image (JSON success only)
        # then fetch the result page ONCE at the end for all BBCode/URLs/gallery_id.
        if hasattr(self.uploader, 'fetch_batch_results'):
            try:
                batch = self.uploader.fetch_batch_results()
                if batch.get('gallery_id') and not gallery_id:
                    gallery_id = batch['gallery_id']
                    gallery_url = self.uploader.get_gallery_url(gallery_id, gallery_name=gallery_name)
                    results['gallery_url'] = gallery_url
                # Merge per-image BBCode/URLs by filename
                batch_by_name = {
                    img['original_filename'].lower(): img
                    for img in batch.get('images', [])
                }
                for image_data in results['images']:
                    fname = (image_data.get('original_filename') or '').lower()
                    if fname in batch_by_name:
                        b = batch_by_name[fname]
                        image_data['bbcode'] = b.get('bbcode') or image_data.get('bbcode')
                        image_data['image_url'] = b.get('image_url') or image_data.get('image_url')
                        image_data['thumb_url'] = b.get('thumb_url') or image_data.get('thumb_url')
            except Exception as e:
                log(f"Failed to fetch batch results: {e}", level="error", category="uploads")

        # Stats
        end_time = time.time()
        upload_time = end_time - start_time
        try:
            uploaded_size = initial_uploaded_size + sum(
                os.path.getsize(os.path.join(folder_path, img_file)) for img_file, _ in uploaded_images
            )
        except Exception as e:
            log(f"Failed to calculate uploaded size: {e}", level="warning", category="uploads")
            uploaded_size = 0
        transfer_speed = uploaded_size / upload_time if upload_time > 0 else 0

        # Dimensions: use precalculated if available, otherwise calculate from samples
        # Use precalculated dimensions from scanning (should ALWAYS be provided)
        # Scanning happens ONCE when gallery is added, NOT during upload
        if precalculated_dimensions:
            avg_width = getattr(precalculated_dimensions, 'avg_width', 0.0) or 0.0
            avg_height = getattr(precalculated_dimensions, 'avg_height', 0.0) or 0.0
            max_width = getattr(precalculated_dimensions, 'max_width', 0.0) or 0.0
            max_height = getattr(precalculated_dimensions, 'max_height', 0.0) or 0.0
            min_width = getattr(precalculated_dimensions, 'min_width', 0.0) or 0.0
            min_height = getattr(precalculated_dimensions, 'min_height', 0.0) or 0.0
        else:
            # No precalculated dimensions - this should not happen in GUI mode
            # Dimensions should have been calculated during initial scan
            log("WARNING: No precalculated dimensions provided to upload engine!", level="warning", category="uploads")
            avg_width = avg_height = max_width = max_height = min_width = min_height = 0

        # Attach filename and optional dims/sizes to each image entry for richer JSON (CLI parity)
        dims_by_name = image_dimensions_map
        for idx, (fname, data) in enumerate(uploaded_images):
            try:
                size_bytes = os.path.getsize(os.path.join(folder_path, fname))
            except Exception as e:
                log(f"Failed to get size for {fname}: {e}", level="debug", category="uploads")
                size_bytes = 0
            w, h = dims_by_name.get(fname, (0, 0))
            try:
                base, ext = os.path.splitext(fname)
                fname_norm = base + ext.lower()
            except Exception as e:
                log(f"Failed to normalize filename {fname}: {e}", level="debug", category="uploads")
                fname_norm = fname
            # Ensure thumb_url if missing — use uploader's get_thumbnail_url
            t = data.get('thumb_url')
            image_url = data.get('image_url')
            if not t and image_url:
                try:
                    # Extract image ID from URL path (last segment, strip extension)
                    url_path = image_url.rstrip('/').rsplit('/', 1)[-1]
                    img_id = os.path.splitext(url_path)[0] if url_path else ''
                    if img_id:
                        _, ext = os.path.splitext(fname_norm)
                        ext_use = (ext.lower() or '.jpg') if ext else '.jpg'
                        t = self.uploader.get_thumbnail_url(img_id, ext_use)
                except Exception as e:
                    log(f"Failed to generate thumbnail URL: {e}", level="debug", category="uploads")
            data.setdefault('thumb_url', t)
            data.setdefault('original_filename', fname_norm)
            data.setdefault('width', w)
            data.setdefault('height', h)
            data.setdefault('size_bytes', size_bytes)
        # Also enrich the preseed (first) image if present in results
        try:
            if preseed_images:
                first_data = preseed_images[0]
                fname = all_image_files[0]
                try:
                    size_bytes = os.path.getsize(os.path.join(folder_path, fname))
                except Exception as e:
                    log(f"Failed to get preseed size: {e}", level="debug", category="uploads")
                    size_bytes = 0
                w, h = dims_by_name.get(fname, (0, 0))
                try:
                    base, ext = os.path.splitext(fname)
                    fname_norm = base + (ext.lower() if ext else '')
                except Exception as e:
                    log(f"Failed to normalize preseed filename: {e}", level="debug", category="uploads")
                    fname_norm = fname
                t = first_data.get('thumb_url')
                first_image_url = first_data.get('image_url')
                if not t and first_image_url:
                    try:
                        url_path = first_image_url.rstrip('/').rsplit('/', 1)[-1]
                        img_id = os.path.splitext(url_path)[0] if url_path else ''
                        if img_id:
                            _, ext = os.path.splitext(fname_norm)
                            ext_use = (ext.lower() or '.jpg') if ext else '.jpg'
                            t = self.uploader.get_thumbnail_url(img_id, ext_use)
                    except Exception as e:
                        log(f"Failed to generate preseed thumbnail URL: {e}", level="debug", category="uploads")
                first_data.setdefault('thumb_url', t)
                first_data.setdefault('original_filename', fname_norm)
                first_data.setdefault('width', w)
                first_data.setdefault('height', h)
                first_data.setdefault('size_bytes', size_bytes)
        except Exception as e:
            log(f"Failed to enrich preseed image: {e}", level="warning", category="uploads")

        results.update({
            'gallery_id': gallery_id,
            'gallery_name': original_name,
            'upload_time': upload_time,
            'total_size': total_size,
            'uploaded_size': uploaded_size,
            'transfer_speed': transfer_speed,
            'avg_width': avg_width,
            'avg_height': avg_height,
            'max_width': max_width,
            'max_height': max_height,
            'min_width': min_width,
            'min_height': min_height,
            'successful_count': initial_completed + len(uploaded_images),
            'failed_count': len(failed_images),
            'failed_details': failed_images,
            # echo settings for artifact helper
            'thumbnail_size': thumbnail_size,
            'thumbnail_format': thumbnail_format,
            'parallel_batch_size': parallel_batch_size,
            'template_name': template_name,
            'total_images': original_total_images,
            'started_at': datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S'),
        })

        # Emit consolidated success at gallery level when appropriate
        try:
            total_attempted = len(all_image_files)
            if failed_images:
                log(f"[uploads] ✗ Gallery '{gallery_id}' completed with failures in {upload_time:.1f}s ({results['successful_count']}/{total_attempted} images)", level="warning", category="uploads:gallery")
                for fname, reason in failed_images:
                    log(f"[uploads] ✗ {fname}: {reason}", level="warning", category="uploads")
            else:
                # Include gallery name and link for clarity
                try:
                    gname = results.get('gallery_name') or gallery_name
                except Exception as e:
                    log(f"Failed to get gallery name from results: {e}", level="debug", category="uploads")
                    gname = gallery_name

                # Calculate metrics
                size_str = format_binary_size(uploaded_size, precision=2)
                rate_bytes_per_sec = uploaded_size / upload_time if upload_time > 0 else 0
                rate_kib_per_sec = rate_bytes_per_sec / 1024
                rate_str = format_binary_rate(rate_kib_per_sec, precision=2)
                time_per_file = upload_time / results['successful_count'] if results['successful_count'] > 0 else 0

                log(
                    f"[uploads:gallery] ✓ Gallery '{gname}' uploaded in {upload_time:.3f}s ({results['successful_count']} images, {size_str}) [{rate_str}, {time_per_file:.3f}s/file]",
                    level="info",
                    category="uploads:gallery"
                )
        except Exception as e:
            log(f"Failed to log upload completion: {e}", level="error", category="uploads")

        return results
