# Application components

This C4 Level 2 diagram shows the major components inside BBDrop and how they
interact. Each box represents a significant module or subsystem; arrows show the
primary communication paths.

```mermaid
C4Container
    title Container Diagram — BBDrop

    Person(user, "User", "Uploads galleries, views BBCode")

    Container_Boundary(app, "BBDrop Application") {
        Container(gui, "PyQt6 GUI", "Python, PyQt6", "Main window, widgets, dialogs. Signal/slot communication with workers.")
        Container(engine, "Upload Engine", "Python", "Host-agnostic upload orchestration. ThreadPoolExecutor for parallel image uploads.")
        Container(queue, "Queue Store", "Python, SQLite WAL", "Persistent gallery queue. GalleryQueueItem dataclass, QMutex-protected state.")
        Container(img_clients, "Image Host Clients", "Python, pycurl / requests", "ImageHostClient ABC, factory pattern. IMX (requests), Pixhost and Turbo (pycurl).")
        Container(file_client, "File Host Client", "Python, pycurl", "Config-driven pycurl client for 7 file hosts. Thread-local handles.")
        Container(workers, "Upload Workers", "Python, QThread", "UploadWorker, FileHostWorker, RenameWorker. Signal-based progress reporting.")
        Container(creds, "Credential Manager", "Python, cryptography, keyring", "Fernet encryption with CSPRNG master key in OS keyring.")
        Container(proxy_pool, "Proxy Pool", "Python, pycurl", "3-level resolver (global / category / service), health checking, Tor integration.")
        Container(archive, "Archive Manager", "Python", "ZIP/7Z creation and extraction with configurable compression and split sizes.")
    }

    System_Ext(image_hosts, "Image Hosts", "IMX.to, Pixhost, TurboImageHost")
    System_Ext(file_hosts, "File Hosts", "RapidGator, Keep2Share, FileBoom, TezFiles, Filedot, Filespace, Katfile")
    System_Ext(keyring, "OS Keyring", "Platform credential storage")

    Rel(user, gui, "Interacts with")
    Rel(gui, queue, "Reads and writes gallery queue")
    Rel(gui, workers, "Starts workers, receives signals")
    Rel(workers, engine, "Delegates upload orchestration")
    Rel(workers, queue, "Updates gallery state")
    Rel(engine, img_clients, "Calls ImageHostClient ABC methods")
    Rel(workers, file_client, "Uploads archive files")
    Rel(img_clients, image_hosts, "HTTP uploads")
    Rel(file_client, file_hosts, "HTTP uploads")
    Rel(img_clients, proxy_pool, "Resolves proxy per host")
    Rel(file_client, proxy_pool, "Resolves proxy per host")
    Rel(img_clients, creds, "Retrieves API keys and passwords")
    Rel(file_client, creds, "Retrieves credentials")
    Rel(creds, keyring, "Reads/writes master key")
    Rel(workers, archive, "Creates archives for file host uploads")
```

## Component roles

- **PyQt6 GUI** (`src/gui/`) --- the main window (`BBDropGUI`, ~3500 lines),
  drag-and-drop queue table, settings dialogs, BBCode viewer, and system tray.
  Communicates with background workers exclusively through pyqtSignal/slot
  connections.

- **Upload Engine** (`src/core/engine.py`) --- the host-agnostic upload loop.
  Accepts any `ImageHostClient` implementation and runs parallel uploads via
  `ThreadPoolExecutor`. Uses `AtomicCounter` for thread-safe byte tracking
  across upload threads.

- **Queue Store** (`src/storage/database.py`, `src/storage/queue_manager.py`)
  --- SQLite database in WAL mode for concurrent readers. `QueueManager` wraps
  the store with `QMutex`-protected state transitions and pyqtSignal
  notifications for GUI updates.

- **Image Host Clients** (`src/network/`) --- the `ImageHostClient` ABC defines
  `upload_image()`, `normalize_response()`, and `get_default_headers()`. The
  factory (`image_host_factory.py`) returns the correct implementation based on
  host ID. `ImxToUploader` uses `requests`; `TurboImageHostClient` and
  `PixhostClient` use pycurl with thread-local handles.

- **File Host Client** (`src/network/file_host_client.py`) --- a single
  pycurl-based client that handles all 7 file hosts. Upload flow, auth method,
  and response parsing are configured declaratively via JSON files in
  `assets/hosts/`.

- **Upload Workers** (`src/processing/`) --- `QThread` subclasses that bridge
  the GUI and the engine. `UploadWorker` handles image host galleries,
  `FileHostWorker` handles file host uploads, and `RenameWorker` handles
  IMX-specific gallery renaming. All communicate results back to the GUI via
  pyqtSignal.

- **Credential Manager** (`src/utils/credentials.py`) --- encrypts credentials
  with Fernet (AES-128-CBC + HMAC-SHA256) using a CSPRNG master key stored in
  the OS keyring. See [ADR-003](../decisions/003-credential-storage.md).

- **Proxy Pool** (`src/proxy/`) --- resolves proxies at three levels (global,
  category, per-service), performs health checks, and integrates with Tor for
  circuit rotation. The pycurl adapter (`pycurl_adapter.py`) configures proxy
  settings on curl handles.

- **Archive Manager** (`src/services/archive_service.py`) --- creates ZIP and
  7Z archives with configurable compression levels and split sizes for file host
  uploads.
