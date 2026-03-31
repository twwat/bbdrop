# Application components

This diagram shows the major components inside BBDrop and how they interact.
Each box represents a significant module or subsystem; arrows show the primary
communication paths.

```mermaid
graph TD
    user(("👤 User"))

    subgraph app ["BBDrop Application"]
        gui["PyQt6 GUI<br/><small>Main window, widgets, dialogs</small>"]
        workers["Upload Workers<br/><small>UploadWorker, FileHostWorker, RenameWorker</small>"]
        engine["Upload Engine<br/><small>Host-agnostic orchestration, ThreadPoolExecutor</small>"]
        queue["Queue Store<br/><small>SQLite WAL, QMutex-protected state</small>"]
        img_clients["Image Host Clients<br/><small>ImageHostClient ABC, factory pattern</small>"]
        file_client["File Host Client<br/><small>Config-driven pycurl, 7 hosts</small>"]
        archive["Archive Manager<br/><small>ZIP/7Z creation, split sizes</small>"]
        creds["Credential Manager<br/><small>Fernet encryption, CSPRNG master key</small>"]
        proxy_pool["Proxy Pool<br/><small>3-level resolver, health checks, Tor</small>"]
    end

    image_hosts[/"IMX.to · Pixhost · TurboImageHost"/]
    file_hosts[/"RapidGator · Keep2Share · FileBoom<br/>TezFiles · Filedot · Filespace · Katfile"/]
    keyring[("OS Keyring")]

    user --> gui
    gui -- "reads/writes queue" --> queue
    gui -- "starts workers, receives signals" --> workers
    workers -- "delegates orchestration" --> engine
    workers -- "updates state" --> queue
    workers -- "creates archives" --> archive
    workers -- "uploads archives" --> file_client
    engine -- "calls ABC methods" --> img_clients
    img_clients -- "HTTP uploads" --> image_hosts
    file_client -- "HTTP uploads" --> file_hosts
    img_clients -.-> proxy_pool
    file_client -.-> proxy_pool
    img_clients -.-> creds
    file_client -.-> creds
    creds --> keyring
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
