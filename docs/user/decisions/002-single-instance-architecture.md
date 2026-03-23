# ADR-002: Single-instance architecture

**Status:** Accepted
**Date:** 2025-01-15

## Context

Users often launch BBDrop multiple times --- for example, by right-clicking
several folders in Windows Explorer and selecting "Add to BBDrop" in quick
succession. Running multiple instances simultaneously would cause:

- **SQLite WAL conflicts.** The queue database (`bbdrop.db`) uses WAL mode for
  concurrent readers, but multiple writers from separate processes risk
  corruption or lock contention.
- **Duplicate uploads.** Two instances reading the same queue could upload the
  same gallery twice.
- **Resource contention.** Concurrent instances would compete for bandwidth,
  disk I/O, and API rate limits.

The application needs a way to ensure only one instance runs at a time while
still accepting folder paths from subsequent launch attempts.

## Decision

Use a **TCP server on `127.0.0.1:27849`** for single-instance enforcement and
inter-process communication.

The mechanism has two components:

### 1. SingleInstanceServer (running instance)

The first instance starts a `SingleInstanceServer` (a `QThread` subclass) that
binds to `127.0.0.1:27849` and listens for incoming connections. When a
connection arrives, the server reads a UTF-8 message (up to 1024 bytes) and
emits a `folder_received` pyqtSignal. The main window's slot handles either:

- **Non-empty string** --- a folder path to add to the upload queue.
- **Empty string** --- a request to bring the existing window to the foreground.

### 2. check_single_instance() (new instance)

On startup, `bbdrop.py` calls `check_single_instance(folder_path)` before
creating the main window. This function attempts to connect to
`127.0.0.1:27849`:

- **Connection succeeds** --- another instance is running. The function sends
  the folder path (or an empty string), then returns `True`. The new process
  exits immediately.
- **Connection fails** --- no instance is running. The function returns `False`,
  and startup continues normally.

The port number `27849` is defined as `COMMUNICATION_PORT` in
`src/core/constants.py`.

## Consequences

**Positive:**

- No database corruption from concurrent writers --- only one process ever
  accesses `bbdrop.db`.
- Seamless UX: right-clicking multiple folders adds them all to the running
  instance's queue without the user needing to switch windows.
- No duplicate uploads from accidental double-launches.

**Negative:**

- Port 27849 must be available on localhost. If another application binds to
  that port, the server falls back to retry logic (3 attempts with 1-second
  delays) but will fail if the port remains unavailable.
- The IPC protocol is unencrypted and unauthenticated. This is acceptable
  because it only listens on `127.0.0.1` (not reachable from the network) and
  the only action a message can trigger is adding a folder path to the queue.
- The 1024-byte message limit restricts folder path length. In practice, this
  is sufficient for filesystem paths.

**Alternative considered:**

- **File-based lock (PID file)** --- rejected because it doesn't support IPC.
  A lock file can prevent concurrent launches, but it can't forward folder
  paths from a new instance to the running one. The TCP approach solves both
  problems in one mechanism.
