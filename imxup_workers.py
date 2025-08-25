"""
Worker threads for ImxUp application.
Handles background upload and completion tasks.
"""

import os
import time
import traceback
from typing import Dict, Any, Optional, Set
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from imxup import ImxToUploader, save_gallery_artifacts, generate_bbcode_from_template
from imxup import rename_all_unnamed_with_session, get_central_storage_path
from imxup_core import UploadEngine
from imxup_constants import (
    QUEUE_STATE_UPLOADING, QUEUE_STATE_COMPLETED, QUEUE_STATE_FAILED,
    QUEUE_STATE_INCOMPLETE, QUEUE_STATE_PAUSED, DEFAULT_PARALLEL_BATCH_SIZE,
    DEFAULT_THUMBNAIL_SIZE, DEFAULT_THUMBNAIL_FORMAT, DEFAULT_PUBLIC_GALLERY,
    MAX_RETRIES
)
from imxup_exceptions import UploadError, WorkerError


class UploadWorker(QThread):
    """Worker thread for uploading galleries"""
    
    # Signals
    progress_updated = pyqtSignal(str, int, int, int, str)  # path, completed, total, progress%, current_image
    gallery_started = pyqtSignal(str, int)  # path, total_images
    gallery_completed = pyqtSignal(str, dict)  # path, results
    gallery_failed = pyqtSignal(str, str)  # path, error_message
    gallery_exists = pyqtSignal(str, list)  # gallery_name, existing_files
    gallery_renamed = pyqtSignal(str)  # gallery_id
    log_message = pyqtSignal(str)
    bandwidth_updated = pyqtSignal(float)  # current KB/s across active uploads
    queue_stats = pyqtSignal(dict)  # aggregate status stats for GUI updates
    
    def __init__(self, queue_manager):
        super().__init__()
        self.queue_manager = queue_manager
        self.uploader = None
        self.running = False
        self.paused = False
        self.mutex = QMutex()
        self.upload_engine = None
        self.current_gallery_path = None
        self._stop_current = False
        self._uploaded_images: Set[str] = set()
        self._bandwidth_tracker = BandwidthTracker()
    
    def initialize_uploader(self):
        """Initialize the uploader instance"""
        try:
            self.uploader = ImxToUploader()
            self.upload_engine = UploadEngine(self.uploader)
            return True
        except Exception as e:
            self.log_message.emit(f"Failed to initialize uploader: {e}")
            return False
    
    def run(self):
        """Main worker thread loop"""
        self.running = True
        
        if not self.initialize_uploader():
            return
        
        while self.running:
            if self.paused:
                self.msleep(100)
                continue
            
            # Get next item from queue
            item = self.queue_manager.get_next_queued_item()
            if not item:
                # Auto-rename check when idle
                self._check_auto_rename()
                self.msleep(1000)
                continue
            
            self.current_gallery_path = item.path
            self._stop_current = False
            self._uploaded_images.clear()
            
            # Update status to uploading
            self.queue_manager.update_item_status(item.path, QUEUE_STATE_UPLOADING)
            
            # Start upload
            self._upload_gallery(item)
            
            self.current_gallery_path = None
    
    def _upload_gallery(self, item):
        """Upload a single gallery"""
        try:
            # Emit start signal
            self.gallery_started.emit(item.path, item.total_images)
            
            # Configure upload parameters
            config = self._get_upload_config()
            
            # Progress callback
            def on_progress(completed, total, percent, current_image):
                if not self._stop_current:
                    self.progress_updated.emit(item.path, completed, total, percent, current_image)
                    self._update_bandwidth_stats(completed, total)
            
            # Log callback
            def on_log(message):
                self.log_message.emit(message)
            
            # Soft stop callback
            def should_stop():
                return self._stop_current or not self.running
            
            # Image uploaded callback for resume support
            def on_image_uploaded(filename, data, size_bytes):
                self._uploaded_images.add(filename)
                self._bandwidth_tracker.add_transfer(size_bytes)
            
            # Run upload
            results = self.upload_engine.run(
                folder_path=item.path,
                gallery_name=item.name,
                thumbnail_size=config['thumbnail_size'],
                thumbnail_format=config['thumbnail_format'],
                max_retries=config['max_retries'],
                public_gallery=config['public_gallery'],
                parallel_batch_size=config['parallel_batch_size'],
                template_name=item.template_name,
                already_uploaded=self._uploaded_images if item.status == QUEUE_STATE_INCOMPLETE else None,
                on_progress=on_progress,
                on_log=on_log,
                should_soft_stop=should_stop,
                on_image_uploaded=on_image_uploaded
            )
            
            # Handle results
            if self._stop_current:
                # Gallery was stopped
                self.queue_manager.update_item_status(item.path, QUEUE_STATE_PAUSED)
            elif results.get('failed_count', 0) > 0:
                # Partial failure
                self.queue_manager.update_item_status(item.path, QUEUE_STATE_INCOMPLETE)
                self.gallery_failed.emit(item.path, f"Failed to upload {results['failed_count']} images")
            else:
                # Success
                self.queue_manager.update_item_status(item.path, QUEUE_STATE_COMPLETED)
                self.gallery_completed.emit(item.path, results)
                
                # Save artifacts
                self._save_artifacts(item, results)
                
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            self.log_message.emit(f"Error uploading {item.path}: {error_msg}")
            self.queue_manager.update_item_status(item.path, QUEUE_STATE_FAILED)
            self.gallery_failed.emit(item.path, error_msg)
    
    def _get_upload_config(self) -> Dict[str, Any]:
        """Get upload configuration from settings"""
        from PyQt6.QtCore import QSettings
        settings = QSettings("ImxUploader", "ImxUploadGUI")
        
        return {
            'thumbnail_size': settings.value("upload/thumbnail_size", DEFAULT_THUMBNAIL_SIZE, type=int),
            'thumbnail_format': settings.value("upload/thumbnail_format", DEFAULT_THUMBNAIL_FORMAT, type=int),
            'max_retries': settings.value("upload/max_retries", MAX_RETRIES, type=int),
            'public_gallery': settings.value("upload/public_gallery", DEFAULT_PUBLIC_GALLERY, type=int),
            'parallel_batch_size': settings.value("upload/parallel_batch_size", DEFAULT_PARALLEL_BATCH_SIZE, type=int)
        }
    
    def _save_artifacts(self, item, results):
        """Save gallery artifacts (JSON and BBCode)"""
        try:
            central_path = get_central_storage_path()
            
            # Generate BBCode
            bbcode = generate_bbcode_from_template(item.template_name, results)
            
            # Save artifacts
            save_gallery_artifacts(
                central_path, 
                results['gallery_name'],
                results['gallery_id'],
                results,
                bbcode
            )
            
            self.log_message.emit(f"Artifacts saved for gallery: {results['gallery_name']}")
            
        except Exception as e:
            self.log_message.emit(f"Failed to save artifacts: {e}")
    
    def _check_auto_rename(self):
        """Check for galleries that need renaming"""
        try:
            if self.uploader:
                renamed_count = rename_all_unnamed_with_session(self.uploader)
                if renamed_count > 0:
                    self.log_message.emit(f"Auto-renamed {renamed_count} galleries")
        except Exception:
            pass
    
    def _update_bandwidth_stats(self, completed, total):
        """Update bandwidth statistics"""
        try:
            current_rate = self._bandwidth_tracker.get_current_rate()
            self.bandwidth_updated.emit(current_rate)
            
            # Emit queue statistics
            stats = self.queue_manager.get_queue_stats()
            self.queue_stats.emit(stats)
            
        except Exception:
            pass
    
    def stop_current_upload(self):
        """Stop the current upload gracefully"""
        with QMutexLocker(self.mutex):
            self._stop_current = True
    
    def pause(self):
        """Pause the worker"""
        with QMutexLocker(self.mutex):
            self.paused = True
    
    def resume(self):
        """Resume the worker"""
        with QMutexLocker(self.mutex):
            self.paused = False
    
    def stop(self):
        """Stop the worker thread"""
        with QMutexLocker(self.mutex):
            self.running = False
            self._stop_current = True
        self.wait()


class CompletionWorker(QThread):
    """Worker thread for completing gallery processing tasks"""
    
    # Signals
    log_message = pyqtSignal(str)
    gallery_renamed = pyqtSignal(str, str)  # gallery_id, new_name
    processing_complete = pyqtSignal(str)  # gallery_path
    
    def __init__(self, uploader: ImxToUploader):
        super().__init__()
        self.uploader = uploader
        self.tasks = []
        self.mutex = QMutex()
    
    def add_task(self, task_type: str, **kwargs):
        """Add a task to the completion queue"""
        with QMutexLocker(self.mutex):
            self.tasks.append({
                'type': task_type,
                'params': kwargs
            })
    
    def run(self):
        """Process completion tasks"""
        while self.tasks:
            with QMutexLocker(self.mutex):
                if not self.tasks:
                    break
                task = self.tasks.pop(0)
            
            try:
                if task['type'] == 'rename':
                    self._rename_gallery(**task['params'])
                elif task['type'] == 'visibility':
                    self._set_visibility(**task['params'])
                elif task['type'] == 'cleanup':
                    self._cleanup_gallery(**task['params'])
                    
            except Exception as e:
                self.log_message.emit(f"Completion task failed: {e}")
    
    def _rename_gallery(self, gallery_id: str, new_name: str):
        """Rename a gallery"""
        try:
            success = self.uploader.rename_gallery_with_session(gallery_id, new_name)
            if success:
                self.gallery_renamed.emit(gallery_id, new_name)
                self.log_message.emit(f"Gallery {gallery_id} renamed to: {new_name}")
            else:
                self.log_message.emit(f"Failed to rename gallery {gallery_id}")
        except Exception as e:
            self.log_message.emit(f"Rename error: {e}")
    
    def _set_visibility(self, gallery_id: str, public: bool):
        """Set gallery visibility"""
        try:
            visibility = 1 if public else 0
            success = self.uploader.set_gallery_visibility(gallery_id, visibility)
            if success:
                status = "public" if public else "private"
                self.log_message.emit(f"Gallery {gallery_id} set to {status}")
            else:
                self.log_message.emit(f"Failed to update visibility for {gallery_id}")
        except Exception as e:
            self.log_message.emit(f"Visibility update error: {e}")
    
    def _cleanup_gallery(self, gallery_path: str):
        """Cleanup gallery resources"""
        try:
            # Perform any cleanup needed
            self.processing_complete.emit(gallery_path)
        except Exception as e:
            self.log_message.emit(f"Cleanup error: {e}")


class BandwidthTracker:
    """Track upload bandwidth statistics"""
    
    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.transfers = []  # List of (timestamp, bytes) tuples
        self.mutex = QMutex()
    
    def add_transfer(self, size_bytes: int):
        """Add a transfer to the tracker"""
        with QMutexLocker(self.mutex):
            current_time = time.time()
            self.transfers.append((current_time, size_bytes))
            
            # Clean old entries
            cutoff_time = current_time - self.window_size
            self.transfers = [(t, b) for t, b in self.transfers if t > cutoff_time]
    
    def get_current_rate(self) -> float:
        """Get current transfer rate in KB/s"""
        with QMutexLocker(self.mutex):
            if len(self.transfers) < 2:
                return 0.0
            
            current_time = time.time()
            cutoff_time = current_time - self.window_size
            
            # Filter recent transfers
            recent = [(t, b) for t, b in self.transfers if t > cutoff_time]
            
            if not recent:
                return 0.0
            
            # Calculate rate
            total_bytes = sum(b for _, b in recent)
            time_span = current_time - recent[0][0]
            
            if time_span > 0:
                return (total_bytes / time_span) / 1024.0  # KB/s
            
            return 0.0
    
    def reset(self):
        """Reset the tracker"""
        with QMutexLocker(self.mutex):
            self.transfers.clear()