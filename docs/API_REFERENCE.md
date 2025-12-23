# IMXuploader API Reference

**Version:** 0.6.06
**Last Updated:** 2025-12-15

This document provides comprehensive API documentation for the IMXuploader project's core modules and classes.

---

## Table of Contents

1. [Network Layer](#1-network-layer)
   - [FileHostClient](#filehostclient)
2. [Processing Layer](#2-processing-layer)
   - [UploadWorker](#uploadworker)
   - [CompletionWorker](#completionworker)
   - [BandwidthTracker](#bandwidthtracker)
3. [Storage Layer](#3-storage-layer)
   - [QueueStore](#queuestore)
4. [GUI Layer](#4-gui-layer)
   - [ImxUploadGUI](#imxuploadgui)
5. [Core Engine](#5-core-engine)
   - [UploadEngine](#uploadengine)
   - [AtomicCounter](#atomiccounter)

---

## 1. Network Layer

### Module: `src/network/file_host_client.py`

#### Overview
Provides pycurl-based file host upload client with bandwidth tracking, progress callbacks, and automatic token refresh for various authentication schemes.

---

### FileHostClient

**Purpose:** Handles file uploads to external file hosting services with support for multiple authentication methods, bandwidth tracking, and automatic token refresh.

#### Constructor

```python
def __init__(
    self,
    host_config: HostConfig,
    bandwidth_counter: AtomicCounter,
    credentials: Optional[str] = None,
    host_id: Optional[str] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
    session_cookies: Optional[Dict[str, str]] = None,
    session_token: Optional[str] = None,
    session_timestamp: Optional[float] = None
)
```

**Parameters:**
- `host_config` (HostConfig): Host configuration object containing API endpoints and auth settings
- `bandwidth_counter` (AtomicCounter): Atomic counter for bandwidth tracking across threads
- `credentials` (Optional[str]): Credentials in format "username:password" or API key
- `host_id` (Optional[str]): Host identifier for token caching
- `log_callback` (Optional[Callable]): Callback function for logging (signature: `func(message: str, level: str)`)
- `session_cookies` (Optional[Dict]): Existing session cookies to reuse
- `session_token` (Optional[str]): Existing session token (sess_id) to reuse
- `session_timestamp` (Optional[float]): Timestamp when session was created

**Attributes:**
- `config` (HostConfig): Host configuration
- `bandwidth_counter` (AtomicCounter): Bandwidth tracking counter
- `auth_token` (Optional[str]): Current authentication token
- `cookie_jar` (Dict[str, str]): Session cookies for session-based auth
- `current_speed_bps` (float): Current upload speed in bytes per second

#### Key Public Methods

##### upload_file
```python
def upload_file(
    self,
    file_path: Path,
    on_progress: Optional[Callable[[int, int, float], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None
) -> Dict[str, Any]
```

Upload a file to the configured file host.

**Parameters:**
- `file_path` (Path): Path to file to upload
- `on_progress` (Optional[Callable]): Progress callback with signature `(uploaded_bytes: int, total_bytes: int, speed_bps: float)`
- `should_stop` (Optional[Callable]): Cancellation check callback returning `bool`

**Returns:**
- `Dict[str, Any]`: Upload result dictionary with keys:
  - `status` (str): "success" or error status
  - `url` (str): Download URL for uploaded file
  - `file_id` (str): File ID for delete operations
  - `raw_response` (Any): Raw API response

**Raises:**
- `Exception`: If upload fails

---

##### delete_file
```python
def delete_file(self, file_id: str) -> Dict[str, Any]
```

Delete a file from the host. Automatically refreshes stale tokens and retries on auth failures.

**Parameters:**
- `file_id` (str): File ID to delete

**Returns:**
- `Dict[str, Any]`: Result dictionary with keys:
  - `status` (str): "success"
  - `file_id` (str): Deleted file ID
  - `raw_response` (str): Response text

**Raises:**
- `Exception`: If delete fails or not supported

---

##### get_user_info
```python
def get_user_info(self) -> Dict[str, Any]
```

Get user account information including storage and premium status.

**Returns:**
- `Dict[str, Any]`: User info dictionary with keys:
  - `storage_total` (int): Total storage in bytes
  - `storage_used` (int): Used storage in bytes
  - `storage_left` (int): Remaining storage in bytes
  - `is_premium` (Optional[bool]): Premium status
  - `raw_response` (Any): Raw API response

**Raises:**
- `ValueError`: If user info retrieval fails or not supported

---

##### test_credentials
```python
def test_credentials(self) -> Dict[str, Any]
```

Test if credentials are valid.

**Returns:**
- `Dict[str, Any]`: Test result with keys:
  - `success` (bool): Whether credentials are valid
  - `message` (str): Status message
  - `user_info` (Optional[Dict]): User info if validation succeeded
  - `error` (Optional[str]): Error message if validation failed

---

##### test_upload
```python
def test_upload(self, cleanup: bool = True) -> Dict[str, Any]
```

Test upload by uploading a small dummy file.

**Parameters:**
- `cleanup` (bool): If True, delete test file after upload

**Returns:**
- `Dict[str, Any]`: Test result with keys:
  - `success` (bool): Whether upload succeeded
  - `message` (str): Status message
  - `file_id` (Optional[str]): Uploaded file ID
  - `url` (Optional[str]): Download URL

---

##### get_session_state
```python
def get_session_state(self) -> Dict[str, Any]
```

Extract current session state for persistence.

**Returns:**
- `Dict[str, Any]`: Session state with keys:
  - `cookies` (Dict[str, str]): Session cookies
  - `token` (Optional[str]): Session token
  - `timestamp` (Optional[float]): Token timestamp

---

#### Important Constants

- `DEFAULT_INACTIVITY_TIMEOUT` = 300 seconds
- `DEFAULT_UPLOAD_TIMEOUT` = None (unlimited)

**Configuration via INI:**
File hosts can override timeout settings in `config/file_hosts.ini`:
```ini
[host_name]
inactivity_timeout = 300  # seconds
upload_timeout = 3600     # seconds
```

---

## 2. Processing Layer

### Module: `src/processing/upload_workers.py`

#### Overview
Background worker threads for uploading galleries and tracking completion. Handles concurrent uploads, bandwidth monitoring, and progress reporting.

---

### UploadWorker

**Purpose:** QThread worker for uploading galleries in the background with progress tracking and bandwidth monitoring.

#### Constructor

```python
def __init__(self, queue_manager: QueueManager)
```

**Parameters:**
- `queue_manager` (QueueManager): Queue manager instance for accessing gallery queue

**Attributes:**
- `queue_manager` (QueueManager): Queue manager reference
- `uploader` (Optional[GUIImxToUploader]): Uploader instance (initialized in run())
- `running` (bool): Worker running state
- `current_item` (Optional[GalleryQueueItem]): Currently processing item
- `global_byte_counter` (AtomicCounter): Persistent byte counter across all galleries
- `current_gallery_counter` (Optional[AtomicCounter]): Per-gallery byte counter
- `auto_rename_enabled` (bool): Whether to auto-rename galleries

#### Signals

```python
progress_updated = pyqtSignal(str, int, int, int, str)
# path, completed, total, progress%, current_image

gallery_started = pyqtSignal(str, int)
# path, total_images

gallery_completed = pyqtSignal(str, dict)
# path, results

gallery_failed = pyqtSignal(str, str)
# path, error_message

gallery_exists = pyqtSignal(str, list)
# gallery_name, existing_files

gallery_renamed = pyqtSignal(str)
# gallery_id

ext_fields_updated = pyqtSignal(str, dict)
# path, ext_fields dict (for hook results)

log_message = pyqtSignal(str)

queue_stats = pyqtSignal(dict)
# aggregate status stats

bandwidth_updated = pyqtSignal(float)
# Instantaneous KB/s from pycurl
```

#### Key Public Methods

##### stop
```python
def stop(self) -> None
```

Stop the worker thread gracefully.

---

##### request_soft_stop_current
```python
def request_soft_stop_current(self) -> None
```

Request to stop the current item after in-flight uploads finish (soft stop).

---

##### run
```python
def run(self) -> None
```

Main worker thread loop. Continuously processes items from queue until stopped.

**Workflow:**
1. Initialize uploader and RenameWorker
2. Loop while `running`:
   - Get next queued item
   - Process based on status (queued/paused)
   - Upload gallery if queued
   - Emit queue stats
   - Sleep if no items

---

### CompletionWorker

**Purpose:** QThread worker for handling gallery completion tasks in background to avoid GUI blocking.

#### Constructor

```python
def __init__(self, parent=None)
```

#### Signals

```python
bbcode_generated = pyqtSignal(str, str)  # path, bbcode
log_message = pyqtSignal(str)
artifact_written = pyqtSignal(str, dict)  # path, written_files
```

#### Key Public Methods

##### add_completion_task
```python
def add_completion_task(self, item: GalleryQueueItem, results: dict) -> None
```

Queue a completion task for background processing.

**Parameters:**
- `item` (GalleryQueueItem): Completed gallery item
- `results` (dict): Upload results dictionary

---

##### stop
```python
def stop(self) -> None
```

Stop the completion worker thread.

---

### BandwidthTracker

**Purpose:** Background thread for tracking upload bandwidth.

#### Constructor

```python
def __init__(self, upload_worker: Optional[UploadWorker] = None)
```

**Parameters:**
- `upload_worker` (Optional[UploadWorker]): Upload worker to track

#### Signals

```python
bandwidth_updated = pyqtSignal(float)  # KB/s
```

#### Key Public Methods

##### stop
```python
def stop(self) -> None
```

Stop bandwidth tracking.

---

## 3. Storage Layer

### Module: `src/storage/database.py`

#### Overview
SQLite-backed storage for uploader internal state. Provides CRUD operations for galleries, images, tabs, and file host uploads.

---

### QueueStore

**Purpose:** Storage facade for queue state in SQLite with WAL mode for concurrent access.

#### Constructor

```python
def __init__(self, db_path: Optional[str] = None)
```

**Parameters:**
- `db_path` (Optional[str]): Path to SQLite database file (default: `~/.imxup/imxup.db`)

**Database Schema:**
- `galleries`: Gallery metadata and upload state
- `images`: Per-image upload tracking
- `tabs`: Tab management
- `unnamed_galleries`: Galleries pending rename
- `file_host_uploads`: External file host upload tracking
- `settings`: Application settings

#### Key Public Methods

##### bulk_upsert
```python
def bulk_upsert(self, items: Iterable[Dict[str, Any]]) -> None
```

Insert or update multiple gallery items.

**Parameters:**
- `items` (Iterable[Dict[str, Any]]): Gallery items to upsert

**Gallery Item Schema:**
- `path` (str): Gallery folder path (unique key)
- `name` (str): Gallery name
- `status` (str): One of: validating, scanning, ready, queued, uploading, paused, incomplete, completed, failed
- `added_time` (int): Unix timestamp when added
- `total_images` (int): Total image count
- `total_size` (int): Total size in bytes
- `gallery_id` (str): IMX gallery ID
- `gallery_url` (str): IMX gallery URL
- `tab_name` (str): Tab assignment
- `custom1-4` (str): Custom field values
- `ext1-4` (str): External program result fields

---

##### bulk_upsert_async
```python
def bulk_upsert_async(self, items: Iterable[Dict[str, Any]]) -> None
```

Async version of bulk_upsert (runs in background thread pool).

---

##### load_all_items
```python
def load_all_items(self) -> List[Dict[str, Any]]
```

Load all gallery items from database.

**Returns:**
- `List[Dict[str, Any]]`: List of gallery dictionaries ordered by insertion_order

---

##### load_items_by_tab
```python
def load_items_by_tab(self, tab_name: str) -> List[Dict[str, Any]]
```

Load galleries filtered by tab name.

**Parameters:**
- `tab_name` (str): Tab name to filter by

**Returns:**
- `List[Dict[str, Any]]`: Filtered gallery list

---

##### delete_by_paths
```python
def delete_by_paths(self, paths: Iterable[str]) -> int
```

Delete galleries by paths.

**Parameters:**
- `paths` (Iterable[str]): Gallery paths to delete

**Returns:**
- `int`: Number of galleries deleted

---

##### update_insertion_orders
```python
def update_insertion_orders(self, ordered_paths: List[str]) -> None
```

Update insertion order for galleries (for drag-drop reordering).

**Parameters:**
- `ordered_paths` (List[str]): Gallery paths in desired order

---

##### Tab Management Methods

###### get_all_tabs
```python
def get_all_tabs(self) -> List[Dict[str, Any]]
```

Get all active tabs ordered by display_order.

**Returns:**
- `List[Dict[str, Any]]`: List of tab dictionaries with keys:
  - `id` (int): Tab ID
  - `name` (str): Tab name
  - `tab_type` (str): "system" or "user"
  - `display_order` (int): Sort order
  - `color_hint` (Optional[str]): Hex color code

---

###### create_tab
```python
def create_tab(
    self,
    name: str,
    color_hint: Optional[str] = None,
    display_order: Optional[int] = None
) -> int
```

Create a new user tab.

**Parameters:**
- `name` (str): Tab name (must be unique)
- `color_hint` (Optional[str]): Hex color code (e.g., '#FF5733')
- `display_order` (Optional[int]): Order position (auto-calculated if None)

**Returns:**
- `int`: Tab ID of created tab

**Raises:**
- `sqlite3.IntegrityError`: If tab name already exists

---

###### update_tab
```python
def update_tab(
    self,
    tab_id: int,
    name: Optional[str] = None,
    display_order: Optional[int] = None,
    color_hint: Optional[str] = None
) -> bool
```

Update an existing tab.

**Parameters:**
- `tab_id` (int): ID of tab to update
- `name` (Optional[str]): New name
- `display_order` (Optional[int]): New display order
- `color_hint` (Optional[str]): New color hint

**Returns:**
- `bool`: True if updated, False if tab not found

**Raises:**
- `ValueError`: If trying to rename system tab
- `sqlite3.IntegrityError`: If name already exists

---

###### delete_tab
```python
def delete_tab(self, tab_id: int, reassign_to: str = 'Main') -> Tuple[bool, int]
```

Delete a tab and reassign its galleries.

**Parameters:**
- `tab_id` (int): ID of tab to delete
- `reassign_to` (str): Tab name to reassign galleries to (default: 'Main')

**Returns:**
- `Tuple[bool, int]`: (success, galleries_reassigned_count)

**Raises:**
- `ValueError`: If trying to delete system tab or invalid tab_id

---

###### move_galleries_to_tab
```python
def move_galleries_to_tab(self, gallery_paths: List[str], new_tab_name: str) -> int
```

Move multiple galleries to a different tab.

**Parameters:**
- `gallery_paths` (List[str]): Gallery paths to move
- `new_tab_name` (str): Destination tab name

**Returns:**
- `int`: Number of galleries moved

**Raises:**
- `ValueError`: If new_tab_name is invalid

---

##### File Host Upload Methods

###### add_file_host_upload
```python
def add_file_host_upload(
    self,
    gallery_path: str,
    host_name: str,
    status: str = 'pending'
) -> Optional[int]
```

Add a new file host upload record.

**Parameters:**
- `gallery_path` (str): Gallery folder path
- `host_name` (str): File host name (e.g., 'rapidgator')
- `status` (str): Initial status (pending/uploading/completed/failed/cancelled)

**Returns:**
- `Optional[int]`: Upload ID if created, None if failed

---

###### get_file_host_uploads
```python
def get_file_host_uploads(self, gallery_path: str) -> List[Dict[str, Any]]
```

Get all file host uploads for a gallery.

**Parameters:**
- `gallery_path` (str): Gallery folder path

**Returns:**
- `List[Dict[str, Any]]`: Upload records with keys:
  - `id` (int): Upload ID
  - `host_name` (str): File host name
  - `status` (str): Upload status
  - `download_url` (Optional[str]): Download URL
  - `file_id` (Optional[str]): File ID for deletion
  - `error_message` (Optional[str]): Error message

---

###### update_file_host_upload
```python
def update_file_host_upload(self, upload_id: int, **kwargs) -> bool
```

Update a file host upload record.

**Parameters:**
- `upload_id` (int): Upload record ID
- `**kwargs`: Fields to update (status, uploaded_bytes, download_url, etc.)

**Returns:**
- `bool`: True if updated successfully

**Allowed Fields:**
- `status`, `zip_path`, `started_ts`, `finished_ts`
- `uploaded_bytes`, `total_bytes`, `download_url`
- `file_id`, `file_name`, `error_message`
- `raw_response`, `retry_count`

---

###### delete_file_host_upload
```python
def delete_file_host_upload(self, upload_id: int) -> bool
```

Delete a file host upload record.

**Parameters:**
- `upload_id` (int): Upload record ID

**Returns:**
- `bool`: True if deleted

---

##### Unnamed Gallery Methods

###### get_unnamed_galleries
```python
def get_unnamed_galleries(self) -> Dict[str, str]
```

Get all unnamed galleries from database.

**Returns:**
- `Dict[str, str]`: Mapping of gallery_id -> intended_name

---

###### add_unnamed_gallery
```python
def add_unnamed_gallery(self, gallery_id: str, intended_name: str) -> None
```

Add an unnamed gallery to database.

---

###### remove_unnamed_gallery
```python
def remove_unnamed_gallery(self, gallery_id: str) -> bool
```

Remove an unnamed gallery.

**Returns:**
- `bool`: True if removed

---

## 4. GUI Layer

### Module: `src/gui/main_window.py`

#### Overview
Main GUI application window using PyQt6. Provides drag-and-drop interface, queue management, and real-time progress tracking.

---

### ImxUploadGUI

**Purpose:** Main application window coordinating all GUI components and background workers.

#### Constructor

```python
def __init__(self, splash=None)
```

**Parameters:**
- `splash` (Optional[SplashScreen]): Splash screen for startup progress

**Key Attributes:**
- `queue_manager` (QueueManager): Gallery queue manager
- `upload_worker` (UploadWorker): Background upload worker thread
- `archive_coordinator` (ArchiveCoordinator): Archive extraction coordinator
- `tab_manager` (TabManager): Tab management system
- `gallery_table` (GalleryTableWidget): Main gallery table widget

#### Key Public Methods

##### add_folders_to_queue
```python
def add_folders_to_queue(self, folder_paths: List[str]) -> None
```

Add folders to upload queue (supports drag-drop and file dialog).

**Parameters:**
- `folder_paths` (List[str]): List of folder paths to add

---

##### start_uploads
```python
def start_uploads(self) -> None
```

Start processing upload queue.

---

##### pause_uploads
```python
def pause_uploads(self) -> None
```

Pause current uploads (soft stop - finishes in-flight uploads).

---

##### clear_queue
```python
def clear_queue(self, status_filter: Optional[str] = None) -> None
```

Clear queue items matching status filter.

**Parameters:**
- `status_filter` (Optional[str]): Status to filter by (e.g., 'completed', 'failed')

---

##### export_bbcode
```python
def export_bbcode(self, gallery_path: str) -> Optional[str]
```

Export BBCode for a completed gallery.

**Parameters:**
- `gallery_path` (str): Gallery path

**Returns:**
- `Optional[str]`: BBCode string or None if unavailable

---

#### Important Constants

**Status Colors:**
- `STATUS_COLORS` = {
  - 'validating': '#FFA500' (orange)
  - 'scanning': '#1E90FF' (blue)
  - 'ready': '#90EE90' (light green)
  - 'queued': '#FFD700' (gold)
  - 'uploading': '#32CD32' (lime green)
  - 'paused': '#FFA500' (orange)
  - 'incomplete': '#FF8C00' (dark orange)
  - 'completed': '#228B22' (forest green)
  - 'failed': '#DC143C' (crimson)
}

**Configuration Paths:**
- Queue database: `~/.imxup/imxup.db`
- Config file: `~/.imxup/config.ini`
- Logs: `~/.imxup/logs/`

---

## 5. Core Engine

### Module: `src/core/engine.py`

#### Overview
Core upload engine shared by CLI and GUI. Centralizes upload loop, retries, and statistics aggregation.

---

### UploadEngine

**Purpose:** Orchestrates folder upload to imx.to with concurrent uploads, retry logic, and progress tracking.

#### Constructor

```python
def __init__(
    self,
    uploader: Any,
    rename_worker: Any = None,
    global_byte_counter: Optional[AtomicCounter] = None,
    gallery_byte_counter: Optional[AtomicCounter] = None,
    worker_thread: Optional[Any] = None
)
```

**Parameters:**
- `uploader` (Any): Uploader instance implementing `upload_image()` and `create_gallery_with_name()`
- `rename_worker` (Optional[Any]): Optional rename worker for background gallery renaming
- `global_byte_counter` (Optional[AtomicCounter]): Persistent counter across all galleries
- `gallery_byte_counter` (Optional[AtomicCounter]): Per-gallery counter (reset each gallery)
- `worker_thread` (Optional[Any]): Worker thread reference for bandwidth emission

#### Key Public Methods

##### run
```python
def run(
    self,
    folder_path: str,
    gallery_name: Optional[str],
    thumbnail_size: int,
    thumbnail_format: int,
    max_retries: int,
    parallel_batch_size: int,
    template_name: str,
    already_uploaded: Optional[Set[str]] = None,
    existing_gallery_id: Optional[str] = None,
    precalculated_dimensions: Optional[Dict[str, float]] = None,
    on_progress: Optional[ProgressCallback] = None,
    should_soft_stop: Optional[SoftStopCallback] = None,
    on_image_uploaded: Optional[ImageUploadedCallback] = None,
) -> Dict[str, Any]
```

Upload a folder as an imx.to gallery.

**Parameters:**
- `folder_path` (str): Path to folder containing images
- `gallery_name` (Optional[str]): Gallery name (uses folder name if None)
- `thumbnail_size` (int): Thumbnail size (1-5)
- `thumbnail_format` (int): Thumbnail format (1-3)
- `max_retries` (int): Maximum retry attempts for failed uploads
- `parallel_batch_size` (int): Concurrent upload threads
- `template_name` (str): BBCode template name
- `already_uploaded` (Optional[Set[str]]): Set of already-uploaded filenames (for resume)
- `existing_gallery_id` (Optional[str]): Existing gallery ID (for resume/append)
- `precalculated_dimensions` (Optional[Dict]): Pre-calculated image dimensions
- `on_progress` (Optional[ProgressCallback]): Progress callback `(completed, total, percent, current_file)`
- `should_soft_stop` (Optional[SoftStopCallback]): Cancellation check callback `() -> bool`
- `on_image_uploaded` (Optional[ImageUploadedCallback]): Per-image callback `(filename, data, size_bytes)`

**Returns:**
- `Dict[str, Any]`: Upload results with keys:
  - `gallery_url` (str): Gallery URL
  - `gallery_id` (str): Gallery ID
  - `gallery_name` (str): Gallery name
  - `images` (List[Dict]): Uploaded image data
  - `successful_count` (int): Successfully uploaded images
  - `failed_count` (int): Failed images
  - `failed_details` (List[Tuple]): Failed image details
  - `upload_time` (float): Upload duration in seconds
  - `total_size` (int): Total folder size in bytes
  - `uploaded_size` (int): Uploaded data size in bytes
  - `transfer_speed` (float): Average transfer speed (bytes/sec)
  - `avg_width/height` (float): Average image dimensions
  - `max_width/height` (float): Maximum image dimensions
  - `min_width/height` (float): Minimum image dimensions

**Raises:**
- `FileNotFoundError`: If folder not found
- `ValueError`: If no images found in folder

---

### AtomicCounter

**Purpose:** Thread-safe byte counter for tracking upload progress across multiple threads.

#### Constructor

```python
def __init__(self)
```

#### Key Public Methods

##### add
```python
def add(self, amount: int) -> None
```

Add bytes to counter (thread-safe).

**Parameters:**
- `amount` (int): Bytes to add

---

##### get
```python
def get(self) -> int
```

Get current value (thread-safe).

**Returns:**
- `int`: Current byte count

---

##### reset
```python
def reset(self) -> None
```

Reset counter to zero (thread-safe).

---

## Type Aliases and Callbacks

### Progress Callback
```python
ProgressCallback = Callable[[int, int, int, str], None]
# Parameters: (completed, total, percent, current_file)
```

### Soft Stop Callback
```python
SoftStopCallback = Callable[[], bool]
# Returns: True if upload should be stopped
```

### Image Uploaded Callback
```python
ImageUploadedCallback = Callable[[str, Dict[str, Any], int], None]
# Parameters: (filename, image_data, size_bytes)
```

---

## Error Handling

### Common Exception Types

- **FileNotFoundError**: Folder or file not found
- **ValueError**: Invalid configuration or parameters
- **ConnectionError**: Network or API errors
- **sqlite3.IntegrityError**: Database constraint violations
- **pycurl.error**: Upload/network errors from pycurl

### Best Practices

1. **Always handle FileNotFoundError** when uploading folders
2. **Use try-except** around database operations
3. **Check credentials** before upload operations
4. **Validate paths** before passing to storage layer
5. **Use thread-safe methods** (AtomicCounter) in concurrent code

---

## Performance Considerations

### Database Optimization
- Uses WAL mode for concurrent reads/writes
- Batch operations via `bulk_upsert_async()`
- Indexes on frequently queried columns (status, tab_id, path)

### Upload Optimization
- Thread pool for concurrent uploads (default: 4 threads)
- Connection pooling via thread-local sessions
- Bandwidth tracking with minimal overhead (200ms polling)

### GUI Optimization
- Lazy widget creation for table rows (viewport-based)
- Debounced database saves (500ms delay)
- Background workers for I/O operations

---

## Configuration Files

### config/file_hosts.ini
```ini
[rapidgator]
inactivity_timeout = 300
upload_timeout = 3600
enabled = true

[gofile]
inactivity_timeout = 300
enabled = true
```

### ~/.imxup/config.ini
```ini
[SETTINGS]
username = user@example.com
password = <encrypted>
api_key = <encrypted>
parallel_batch_size = 4
thumbnail_size = 3
thumbnail_format = 2
```

---

## Examples

### Example 1: Upload with FileHostClient

```python
from src.network.file_host_client import FileHostClient
from src.core.file_host_config import load_host_config
from src.core.engine import AtomicCounter
from pathlib import Path

# Load host configuration
config = load_host_config('rapidgator')

# Create bandwidth counter
counter = AtomicCounter()

# Initialize client
client = FileHostClient(
    host_config=config,
    bandwidth_counter=counter,
    credentials="username:password",
    host_id="rapidgator"
)

# Upload file with progress
def on_progress(uploaded, total, speed_bps):
    print(f"Progress: {uploaded}/{total} bytes @ {speed_bps/1024:.2f} KB/s")

result = client.upload_file(
    file_path=Path("/path/to/file.zip"),
    on_progress=on_progress
)

print(f"Download URL: {result['url']}")
print(f"File ID: {result['file_id']}")
```

### Example 2: Queue Management

```python
from src.storage.database import QueueStore

# Initialize database
store = QueueStore()

# Add gallery
gallery = {
    'path': '/path/to/gallery',
    'name': 'My Gallery',
    'status': 'ready',
    'tab_name': 'Main',
    'total_images': 50,
    'total_size': 1024000
}
store.bulk_upsert([gallery])

# Load all galleries
items = store.load_all_items()

# Filter by tab
main_items = store.load_items_by_tab('Main')
```

### Example 3: Background Upload Worker

```python
from PyQt6.QtCore import QCoreApplication
from src.processing.upload_workers import UploadWorker
from src.storage.queue_manager import QueueManager

app = QCoreApplication([])

# Initialize queue
queue_mgr = QueueManager()

# Create and start worker
worker = UploadWorker(queue_mgr)

# Connect signals
worker.gallery_completed.connect(
    lambda path, results: print(f"Completed: {path}")
)

worker.start()

# Add items to queue...
# queue_mgr.add_item(...)

app.exec()
```

---

## Version History

- **0.6.06** (2025-12-15): Current version
  - Added file host upload tracking
  - Improved tab management with referential integrity
  - Added custom fields (custom1-4, ext1-4)
  - Performance optimizations for database queries

---

## See Also

- [README.md](../README.md) - Project overview
- [config/file_hosts.json](../config/file_hosts.json) - File host configurations
- [src/utils/logger.py](../src/utils/logger.py) - Logging utilities
- [src/gui/dialogs/](../src/gui/dialogs/) - GUI dialog classes

---

**Document End**
