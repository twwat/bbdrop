"""
File host upload worker threads.

Background workers that process file host upload queue, create ZIPs,
upload to hosts, and emit progress signals to the GUI.
"""

import time
import json
import hashlib
import threading
import traceback
from typing import Optional, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, QSettings

from src.utils.credentials import get_credential, decrypt_password
from src.core.engine import AtomicCounter
from src.core.file_host_config import (
    get_config_manager,
    HostConfig,
    get_file_host_setting,
    get_host_family,
    is_family_dedup_enabled,
)
from src.network.file_host_client import FileHostClient
from src.processing.file_host_coordinator import get_coordinator
from src.proxy.resolver import ProxyResolver
from src.proxy.models import ProxyContext
from src.storage.database import QueueStore
from src.utils.logger import log
from src.utils.archive_manager import get_archive_manager


class FileHostWorker(QThread):
    """Worker thread for file host uploads.

    One worker per enabled host - handles uploads, tests, and storage checks.
    """

    # Spinup retry delay sequence (seconds): 10s, 30s, 90s, 3min, 5min
    SPINUP_RETRY_DELAYS = [10, 30, 90, 180, 300]

    # Default maximum time (seconds) for spinup retry attempts
    SPINUP_RETRY_MAX_TIME_DEFAULT = 600

    # Signals for communication with GUI
    upload_started = pyqtSignal(int, str)  # db_id, host_name
    upload_progress = pyqtSignal(int, str, object, object, float)  # db_id, host_name, uploaded_bytes, total_bytes, speed_bps
    upload_completed = pyqtSignal(int, str, dict)  # db_id, host_name, result_dict
    upload_failed = pyqtSignal(int, str, str)  # db_id, host_name, error_message
    bandwidth_updated = pyqtSignal(str, float)  # host_id, KB/s from pycurl
    log_message = pyqtSignal([str], [str, str])  # Overloaded: (message) or (level, message) for backward compatibility

    # New signals for testing and storage
    storage_updated = pyqtSignal(str, object, object)  # host_id, total_bytes, left_bytes (use object for large ints)
    test_completed = pyqtSignal(str, dict)  # host_id, results_dict
    spinup_complete = pyqtSignal(str, str)  # host_id, error_message (empty = success)
    credentials_update_requested = pyqtSignal(str)  # credentials (for updating credentials from dialog)
    status_updated = pyqtSignal(str, str)  # host_id, status_text

    # Family-coordination signal: emitted once per gallery after the worker's
    # multi-part loop fully terminates for that gallery. Avoids per-part race
    # where a coordinator could observe "all known rows terminal" between
    # iterations of the worker's upload loop.
    host_gallery_settled = pyqtSignal(int, str, bool)  # gallery_fk, host_name, success

    @staticmethod
    def _compute_md5(file_path) -> str:
        """Compute MD5 hash of a file."""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b""):
                md5.update(chunk)
        return md5.hexdigest()

    def __init__(self, host_id: str, queue_store: QueueStore):
        """Initialize file host worker for a specific host.

        Args:
            host_id: Unique host identifier (e.g., 'rapidgator')
            queue_store: Database queue store
        """
        super().__init__()

        self.host_id = host_id
        self.queue_store = queue_store
        self.config_manager = get_config_manager()
        self.coordinator = get_coordinator()
        self.archive_manager = get_archive_manager()
        self.settings = QSettings("BBDropUploader", "BBDropGUI")

        # Get display name for logs (e.g., "RapidGator" instead of "rapidgator")
        host_config = self.config_manager.get_host(host_id)
        self.log_prefix = f"{host_config.name} Worker" if host_config else f"{host_id} Worker"

        self._stop_event = threading.Event()  # Thread-safe stop signal
        self._pause_event = threading.Event()  # Thread-safe pause signal (set = paused)

        # Bandwidth tracking
        self.bandwidth_counter = AtomicCounter()
        self._bw_last_bytes = 0
        self._bw_last_time = time.time()
        self._bw_last_emit = 0.0

        # Load host credentials from settings
        self.host_credentials: Dict[str, str] = {}
        self._credentials_lock = threading.Lock()  # Protects host_credentials access
        self._load_credentials()

        # Persistent session state (shared across all client instances)
        self._session_cookies: Dict[str, str] = {}  # Persists across operations
        self._session_token: Optional[str] = None    # For session_id_regex hosts
        self._session_timestamp: Optional[float] = None
        self._session_lock = threading.Lock()        # Thread safety for session access

        # Test request queue (processed in run() loop to execute in worker thread)
        self._test_queue: list[str] = []  # List of credentials to test
        self._test_queue_lock = threading.Lock()

        # Current upload tracking
        self.current_upload_id: Optional[int] = None
        self.current_host: Optional[str] = None
        self.current_db_id: Optional[int] = None
        self._should_stop_current = False

        # Thread-safe upload throttle state
        self._upload_throttle_state = {}  # {(db_id, host): {'last_emit': time, 'last_progress': (up, total)}}
        self._throttle_lock = threading.Lock()

        # Connect credentials update signal
        self.credentials_update_requested.connect(self._update_credentials)

    def _log(self, message: str, level: str = "info") -> None:
        """Helper to log with host name prefix.

        Args:
            message: Log message
            level: Log level (info, debug, warning, error)
        """
        # Emit signal for any connected dialogs (specify two-argument overload)
        self.log_message[str, str].emit(level, message)

        # Write to file logger
        log(f"{self.log_prefix}: {message}", level=level, category="file_hosts")

    def _load_credentials(self) -> None:
        """Load this host's credentials from OS keyring."""
        encrypted_creds = get_credential(f'file_host_{self.host_id}_credentials')
        if encrypted_creds:
            try:
                credentials = decrypt_password(encrypted_creds)
                if credentials:
                    with self._credentials_lock:
                        self.host_credentials[self.host_id] = credentials
            except Exception as e:
                self._log(f"Failed to decrypt credentials: {e}")

    @pyqtSlot(str)
    def _update_credentials(self, credentials: str) -> None:
        """Update credentials for this host (called via signal from dialog).

        Args:
            credentials: New credentials string (username:password or api_key)
        """
        with self._credentials_lock:
            if credentials:
                self.host_credentials[self.host_id] = credentials
                self._log("Credentials updated from dialog", level="debug")
            else:
                # Empty credentials = remove
                self.host_credentials.pop(self.host_id, None)
                self._log("Credentials cleared", level="debug")

    def _cleanup_upload_throttle_state(self, db_id: int, host_name: str):
        """Clean up throttling state for an upload to prevent memory leaks."""
        with self._throttle_lock:
            self._upload_throttle_state.pop((db_id, host_name), None)

    def _create_client(self, host_config: HostConfig) -> FileHostClient:
        """Create FileHostClient with session reuse and proxy support.

        Thread-safe: Reads session state under lock, injects into new client.

        Args:
            host_config: Host configuration

        Returns:
            Configured FileHostClient instance with session reuse and proxy
        """
        # Resolve proxy for this host
        resolver = ProxyResolver()
        context = ProxyContext(
            category="file_hosts",
            service_id=self.host_id,
            operation="upload"
        )
        proxy = resolver.resolve(context)

        # Log proxy being used (for debugging)
        if proxy:
            self._log(f"Using proxy: {proxy.host}:{proxy.port}", "debug")

        with self._credentials_lock:
            credentials = self.host_credentials.get(self.host_id)

        # Thread-safe read of session state
        with self._session_lock:
            session_cookies = self._session_cookies.copy() if self._session_cookies else None
            session_token = self._session_token
            session_timestamp = self._session_timestamp

        # Create client with session injection and proxy (no login if session exists)
        client = FileHostClient(
            host_config=host_config,
            bandwidth_counter=self.bandwidth_counter,
            credentials=credentials,
            host_id=self.host_id,
            log_callback=self._log,
            # NEW: Inject session (reuse if exists, fresh login if None)
            session_cookies=session_cookies,
            session_token=session_token,
            session_timestamp=session_timestamp,
            proxy=proxy  # Inject proxy
        )

        return client

    def _update_session_from_client(self, client: FileHostClient) -> None:
        """Extract and persist session state from client.

        Thread-safe: Writes session state under lock.

        Args:
            client: FileHostClient instance to extract session from
        """
        session_state = client.get_session_state()

        with self._session_lock:
            self._session_cookies = session_state['cookies']
            self._session_token = session_state['token']
            self._session_timestamp = session_state['timestamp']

        pass  # Session state persisted

    def queue_test_request(self, credentials: str) -> None:
        """Queue a test request to be processed in the worker thread.

        This method is called from the GUI thread and queues the request
        for processing in the worker's run() loop where it executes in
        the worker thread context (non-blocking).

        Args:
            credentials: Credentials to test with
        """
        with self._test_queue_lock:
            self._test_queue.append(credentials)
            self._log("Test request queued", level="debug")

    def stop(self) -> None:
        """Stop the worker thread."""
        self._log("Stopping file host worker...", level="debug")
        self._stop_event.set()
        self.wait()

    def pause(self) -> None:
        """Pause processing new uploads."""
        self._pause_event.set()
        self._log("File host worker paused", level="info")

    def resume(self) -> None:
        """Resume processing uploads."""
        self._pause_event.clear()
        self._log("File host worker resumed", level="info")

    def _wait_with_countdown(self, delay: int, status_prefix: str = "retry_pending") -> bool:
        """Wait with countdown, emitting status updates each second.

        Args:
            delay: Total seconds to wait
            status_prefix: Status prefix for compound status (e.g., "retry_pending")

        Returns:
            True if completed normally, False if stopped early
        """
        for remaining in range(delay, 0, -1):
            if self._stop_event.is_set():
                return False
            self.status_updated.emit(self.host_id, f"{status_prefix}:{remaining}")
            time.sleep(1)
        return True

    def _is_retryable_error(self, error: Exception, error_msg: str) -> bool:
        """
        Determine if an error should trigger a retry attempt.

        Non-retryable errors are permanent failures that won't be fixed by retrying:
        - Folder/file not found
        - Permission denied (folder-level)
        - Invalid path format
        - Not a directory

        Retryable errors are transient network/server issues:
        - Connection errors
        - Timeouts
        - HTTP 5xx errors
        - Rate limits

        Args:
            error: The exception that occurred
            error_msg: Error message string

        Returns:
            bool: True if error should trigger retry, False if should fail immediately
        """
        # Non-retryable error types (permanent failures)
        NON_RETRYABLE_ERRORS = (
            FileNotFoundError,
            NotADirectoryError,
            ValueError,  # Invalid path format
        )

        if isinstance(error, NON_RETRYABLE_ERRORS):
            self._log(f"Error is non-retryable (type: {type(error).__name__}), failing immediately", level="debug")
            return False

        # Check error message for folder/path-related issues
        error_lower = error_msg.lower()
        non_retryable_keywords = [
            'folder not found',
            'does not exist',
            'not a directory',
            'not a folder',
            'invalid path',
            'path does not exist',
            'no such file or directory'
        ]

        if any(keyword in error_lower for keyword in non_retryable_keywords):
            self._log(f"Error message indicates non-retryable issue: {error_msg}", level="debug")
            return False

        # Permission errors - only folder-level permission errors are non-retryable
        # Server-level permission errors (upload denied) may be retryable after re-auth
        if isinstance(error, PermissionError):
            if 'folder' in error_lower or 'directory' in error_lower:
                self._log("Folder permission error is non-retryable", level="debug")
                return False
            # Server permission errors may be retryable
            self._log("Server permission error, allowing retry", level="debug")
            return True

        # All other errors (network, timeout, server errors) are retryable
        self._log(f"Error is retryable (type: {type(error).__name__})", level="debug")
        return True

    def _is_spinup_network_error(self, error: Optional[Exception], error_msg: str) -> bool:
        """Determine if a spinup error is a network error that should trigger retry.

        Network errors are transient and may succeed on retry (DNS, connection, timeout).
        Authentication errors are permanent and should fail immediately.

        Args:
            error: The exception that occurred
            error_msg: Error message string

        Returns:
            True if error is a network error (should retry), False if auth error (no retry)
        """
        error_lower = error_msg.lower()

        # Authentication error patterns - DO NOT RETRY
        auth_error_patterns = [
            "invalid credentials",
            "wrong password",
            "unauthorized",
            "invalid api key",
            "authentication failed",
            "invalid username",
            "account not found",
            "access denied",
            "forbidden",
            "login failed",
            "login blocked",
        ]

        for pattern in auth_error_patterns:
            if pattern in error_lower:
                self._log(f"Error classified as auth (no retry): {error_msg[:100]}", level="debug")
                return False

        # Check for pycurl error codes (network errors)
        # These are indicated in error messages like "pycurl error 7" or "(7)"
        network_pycurl_codes = [6, 7, 28, 35, 52, 55, 56]  # DNS, connect, timeout, SSL, empty response, send/recv errors

        for code in network_pycurl_codes:
            if f"pycurl error {code}" in error_lower or f"({code})" in error_msg:
                self._log(f"Error classified as network/pycurl code {code} (retry allowed): {error_msg[:100]}", level="debug")
                return True

        # Network error string patterns - RETRY
        network_error_patterns = [
            "timeout",
            "timed out",
            "connection refused",
            "dns",
            "ssl",
            "network",
            "connection reset",
            "connection failed",
            "could not resolve",
            "name resolution",
            "socket",
            "unreachable",
        ]

        for pattern in network_error_patterns:
            if pattern in error_lower:
                self._log(f"Error classified as network (retry allowed): {error_msg[:100]}", level="debug")
                return True

        # Default: fail fast on unknown errors to avoid masking new auth error patterns
        self._log(f"Error classified as unknown (no retry): {error_msg[:100]}", level="warning")
        return False

    def _get_spinup_retry_delay(self, retry_num: int) -> int:
        """Get the delay in seconds for a spinup retry attempt.

        Uses exponential backoff with predefined delays: [10, 30, 90, 180, 300].
        For retry attempts beyond the sequence length, caps at 300 seconds.

        Args:
            retry_num: 1-indexed retry number (1 = first retry, 2 = second retry, etc.)

        Returns:
            Delay in seconds before the next retry attempt
        """
        # Convert to 0-indexed for array access
        index = retry_num - 1

        if index < len(self.SPINUP_RETRY_DELAYS):
            return self.SPINUP_RETRY_DELAYS[index]
        else:
            # Cap at maximum delay (300 seconds / 5 minutes)
            return self.SPINUP_RETRY_DELAYS[-1]

    def cancel_current_upload(self) -> None:
        """Cancel the current upload."""
        self._should_stop_current = True
        self._log(
            f"Cancel requested for current upload: {self.current_host} (gallery {self.current_db_id})",
            level="info"
        )

    def run(self):
        """Main worker thread loop - process uploads for this host only."""
        self.status_updated.emit(self.host_id, "starting")
        #log(f"Emitted status signal: {self.host_id} -> starting", level="trace", category="file_hosts")

        # Test credentials during spinup (power button paradigm)
        host_config = self.config_manager.get_host(self.host_id)
        if host_config and host_config.requires_auth:
            with self._credentials_lock:
                credentials = self.host_credentials.get(self.host_id)
            if not credentials:
                error = "Credentials required but not configured"
                self._log(error, level="warning")
                self.spinup_complete.emit(self.host_id, error)
                self._stop_event.set()
                return

            self.status_updated.emit(self.host_id, "authenticating")

            # Load retry settings
            spinup_retry_enabled = get_file_host_setting(self.host_id, "spinup_retry_enabled", "bool")
            spinup_retry_max_time = get_file_host_setting(self.host_id, "spinup_retry_max_time", "int") or self.SPINUP_RETRY_MAX_TIME_DEFAULT

            spinup_success = False
            spinup_error = ""
            last_exception = None
            retry_num = 0
            spinup_start_time = time.time()

            while not self._stop_event.is_set():
                spinup_error = ""
                last_exception = None

                try:
                    client = self._create_client(host_config)
                    cred_result = client.test_credentials()

                    if not cred_result.get('success'):
                        spinup_error = cred_result.get('message', 'Credential validation failed')
                        self._log(f"Credential test failed: {spinup_error}", level="warning")
                    else:
                        # Success - save storage if available
                        user_info = cred_result.get('user_info', {})
                        if user_info:
                            storage_total = user_info.get('storage_total')
                            storage_left = user_info.get('storage_left')
                            if storage_total is not None and storage_left is not None:
                                try:
                                    total = int(storage_total)
                                    left = int(storage_left)
                                    self._save_storage_cache(total, left)
                                    self.storage_updated.emit(self.host_id, total, left)
                                except (ValueError, TypeError) as e:
                                    self._log(f"Failed to parse storage: {e}", level="debug")

                        spinup_success = True
                        self.status_updated.emit(self.host_id, "idle")

                        # Persist session from first login
                        self._update_session_from_client(client)
                        break

                except Exception as e:
                    spinup_error = str(e)
                    last_exception = e
                    self._log(f"Credential test exception: {spinup_error}", level="debug")

                # Handle spinup error (from either credential failure or exception)
                if spinup_error:
                    # Check if this is an auth error (no retry) vs network error (retry)
                    if not spinup_retry_enabled or not self._is_spinup_network_error(last_exception, spinup_error):
                        # Auth error or retry disabled - fail immediately
                        self._log(f"Authentication error, failing immediately: {spinup_error}", level="info")
                        self.status_updated.emit(self.host_id, "failed:Authentication failed")
                        break

                    # Network error - check if we should retry
                    retry_num += 1
                    elapsed_time = time.time() - spinup_start_time
                    if elapsed_time >= spinup_retry_max_time:
                        self._log(f"Max retry time ({spinup_retry_max_time}s) exceeded", level="warning")
                        self.status_updated.emit(self.host_id, "failed:Max retries exhausted")
                        spinup_error = "Max retries exhausted"
                        break

                    # Calculate delay and wait with countdown
                    delay = self._get_spinup_retry_delay(retry_num)
                    self._log(f"Retry {retry_num}: waiting {delay}s...", level="info")

                    # Wait with countdown - returns False if stopped early
                    if not self._wait_with_countdown(delay, "retry_pending"):
                        spinup_error = "Worker stopped during retry"
                        break

                    # After delay, retry authentication
                    self.status_updated.emit(self.host_id, "authenticating")
                    continue

            # ALWAYS emit spinup_complete signal - manager depends on this for cleanup
            # Emit success (empty error) or failure (with error message)
            self.spinup_complete.emit(self.host_id, "" if spinup_success else spinup_error)

            # If spinup failed, stop worker thread
            if not spinup_success:
                self._stop_event.set()
                return
        else:
            # No auth required - immediately signal idle
            self.status_updated.emit(self.host_id, "idle")
            self.spinup_complete.emit(self.host_id, "")

        while not self._stop_event.is_set():
            try:
                if self._pause_event.is_set():
                    time.sleep(0.5)
                    continue

                # Check for test requests (process in worker thread)
                test_credentials = None
                with self._test_queue_lock:
                    if self._test_queue:
                        test_credentials = self._test_queue.pop(0)

                if test_credentials:
                    # Update credentials and run test in worker thread
                    with self._credentials_lock:
                        self.host_credentials[self.host_id] = test_credentials
                    self._log("Processing test request in worker thread", level="debug")
                    self.test_connection()
                    # Continue loop to check for more tests or uploads
                    continue

                # Get next pending upload for THIS host only
                pending_uploads = self.queue_store.get_pending_file_host_uploads(host_name=self.host_id)

                if not pending_uploads:
                    # No work to do, just wait (don't emit 0 bandwidth)
                    time.sleep(1.0)
                    continue

                # Process next upload
                upload = pending_uploads[0]
                host_name = upload['host_name']
                db_id = upload['gallery_fk']
                upload_id = upload['id']
                gallery_path = upload['gallery_path']

                # Convert WSL2 paths and validate folder exists BEFORE marking as uploading
                from src.utils.system_utils import convert_to_wsl_path
                folder_path = convert_to_wsl_path(gallery_path)

                if not folder_path.exists():
                    error_msg = f"Gallery folder not found: {gallery_path}"
                    if str(gallery_path) != str(folder_path):
                        error_msg += f" (tried WSL2 path: {folder_path})"

                    self._log(f"FAIL FAST: {error_msg}", level="warning")
                    # CRITICAL: Emit signal FIRST before DB write (fail-fast path)
                    self.upload_failed.emit(db_id, host_name, error_msg)
                    self.queue_store.update_file_host_upload(
                        upload_id,
                        status='failed',
                        finished_ts=int(time.time()),
                        error_message=error_msg
                    )
                    continue

                if not folder_path.is_dir() and not folder_path.is_file():
                    error_msg = f"Path does not exist: {gallery_path}"
                    self._log(f"FAIL FAST: {error_msg}", level="warning")
                    self.upload_failed.emit(db_id, host_name, error_msg)
                    self.queue_store.update_file_host_upload(
                        upload_id,
                        status='failed',
                        finished_ts=int(time.time()),
                        error_message=error_msg
                    )
                    continue

                # Check if host is enabled (should always be true since worker exists)
                host_config = self.config_manager.get_host(host_name)
                host_enabled = get_file_host_setting(host_name, "enabled", "bool")
                if not host_config or not host_enabled:
                    self._log(
                        f"Host {host_name} is disabled, skipping upload for gallery {db_id}",
                        level="warning")
                    self.queue_store.update_file_host_upload(
                        upload_id,
                        status='failed',
                        error_message=f"Host {host_name} is disabled"
                    )
                    continue

                # Check if we can start upload (connection limits)
                if not self.coordinator.can_start_upload(host_name):
                    self._log(
                        f"Connection limit reached for {host_name}, waiting...",
                        level="debug")
                    time.sleep(1.0)
                    continue

                # Acquire upload slot and process
                try:
                    with self.coordinator.acquire_slot(db_id, host_name, timeout=5.0):
                        self._process_single_pending_row(upload, host_config=host_config)
                except TimeoutError:
                    self._log(
                        f"Could not acquire upload slot for {host_name}, retrying...",
                        level="debug")
                    time.sleep(1.0)

            except Exception as e:
                self._log(f"Error in file host worker loop: {e}", level="error")
                traceback.print_exc()
                time.sleep(1.0)

        self._log("Worker stopped", level="info")

    def _get_or_create_archive(self, db_id, folder_path, gallery_name,
                               archive_format, compression, split_size_mb):
        """Thin wrapper around ArchiveManager.create_or_reuse_archive.

        Exists so tests can monkeypatch archive creation to verify it was (or
        was not) called, without patching a third-party object.
        """
        return self.archive_manager.create_or_reuse_archive(
            db_id=db_id,
            folder_path=folder_path,
            gallery_name=gallery_name,
            archive_format=archive_format,
            compression=compression,
            split_size_mb=split_size_mb,
        )

    def _process_single_pending_row(self, row: dict, client=None, host_config=None):
        """Pre-upload family-mirror branch + delegate to full upload.

        Before any archive creation, attempts a K2S-family hash-dedup mirror
        when the feature is enabled.  Three outcomes:

        1. Mirror succeeds      → mark row completed, emit host_gallery_settled(True), return.
        2. dedup_only miss      → mark row failed terminally, emit host_gallery_settled(False), return.
        3. Normal / mirror miss → fall through to _process_upload (full upload path).

        After _process_upload returns (for path 3), query the DB for the
        aggregate outcome and emit host_gallery_settled.

        Args:
            row:         A dict from get_pending_file_host_uploads.
            client:      Optional FileHostClient. PRODUCTION CALLERS MUST PASS None —
                         the method creates a client internally via self._create_client
                         when the family-mirror branch is triggered. This parameter exists
                         solely for test injection of a mock client; passing a real client
                         from production code would bypass proper client lifecycle and
                         silently skip archive creation if the mirror branch is taken.
            host_config: Optional HostConfig (looked up when None).
        """
        upload_id = row["id"]
        db_id = row["gallery_fk"]
        gallery_path = row["gallery_path"]
        host_name = row["host_name"]

        # Resolve host_config early (needed by both the mirror branch and the
        # full-upload path).
        if host_config is None:
            host_config = self.config_manager.get_host(host_name)

        # --- Family mirror pre-upload branch ---
        # Use caller-supplied client (tests) or build one now if family dedup
        # is enabled and this host belongs to a family.
        family = get_host_family(host_name) if is_family_dedup_enabled() else None
        mirror_client = client  # may be None
        if family and mirror_client is None and host_config is not None:
            try:
                mirror_client = self._create_client(host_config)
            except Exception as e:
                self._log(
                    f"Could not create client for family mirror check: {e}",
                    level="debug",
                )

        mirror_succeeded = False
        if family and mirror_client is not None:
            mirror_succeeded = self._try_family_mirror(row, mirror_client, family)

        if mirror_succeeded:
            # Emit upload_completed so GUI refreshes queue display and artifacts
            self.upload_completed.emit(db_id, host_name, {'status': 'success', 'deduplication': True})
            self.host_gallery_settled.emit(db_id, host_name, True)
            return

        if row.get("dedup_only") == 1:
            # This row exists solely to leverage a sibling's md5.  If the
            # mirror missed it means the backend doesn't have the file yet
            # — no fallback to a full upload.
            self.queue_store.update_file_host_upload(
                upload_id,
                status="failed",
                error_message="family dedup retry could not mirror sibling md5",
                finished_ts=int(time.time()),
            )
            self.host_gallery_settled.emit(db_id, host_name, False)
            return

        # Full upload path: wrap the existing call + aggregate emit in try/finally
        # so host_gallery_settled always fires, even on exception from the upload
        # path. Task 11's HostFamilyCoordinator relies on this signal firing at
        # every terminal point.
        gallery_fk_for_emit = db_id
        gallery_path_for_emit = gallery_path
        try:
            self._process_upload(
                upload_id=upload_id,
                db_id=db_id,
                gallery_path=gallery_path,
                gallery_name=row["gallery_name"],
                host_name=host_name,
                host_config=host_config,
            )
        finally:
            # Emit settled signal based on aggregate outcome for this (gallery, host).
            try:
                final_rows = self.queue_store.get_file_host_uploads(gallery_path_for_emit)
                all_completed = all(
                    r["status"] == "completed"
                    for r in final_rows
                    if r["host_name"] == host_name and r["gallery_fk"] == gallery_fk_for_emit
                )
            except Exception:
                # If even the DB read fails, default to False so the coordinator
                # sees a failure signal and can promote another host.
                all_completed = False
            self.host_gallery_settled.emit(gallery_fk_for_emit, host_name, all_completed)

    def _process_upload(
        self,
        upload_id: int,
        db_id: int,
        gallery_path: str,
        gallery_name: Optional[str],
        host_name: str,
        host_config: HostConfig
    ):
        """Process a single file host upload.

        Args:
            upload_id: Database upload record ID
            db_id: Database ID for the upload
            gallery_path: Path to gallery folder
            gallery_name: Gallery name
            host_name: Host name
            host_config: Host configuration
        """
        self.current_upload_id = upload_id
        self.current_host = host_name
        self.current_db_id = db_id
        self._should_stop_current = False

        # Initialize timing and size tracking for metrics
        upload_start_time = time.time()

        self._log(
            f"Starting upload to {host_name} for gallery {db_id} ({gallery_name})",
            level="debug"
        )

        # CRITICAL: Emit started signal FIRST before database write
        # This ensures GUI gets immediate notification without waiting for DB
        self.upload_started.emit(db_id, host_name)

        # Update status to uploading (AFTER signal emission)
        self.queue_store.update_file_host_upload(
            upload_id,
            status='uploading',
            started_ts=int(time.time())
        )

        archive_created = False  # track whether archive_manager needs releasing
        try:
            # Step 1: Determine upload file(s) — raw file or archive
            from src.utils.system_utils import convert_to_wsl_path
            from src.utils.paths import load_user_defaults
            folder_path = convert_to_wsl_path(gallery_path)

            if not folder_path.exists():
                error_msg = f"Gallery folder not found: {gallery_path}"
                if str(gallery_path) != str(folder_path):
                    error_msg += f" (WSL2 path: {folder_path})"
                raise FileNotFoundError(error_msg)

            is_single_file = folder_path.is_file()

            if is_single_file:
                # Single file (e.g. video): upload raw unless it exceeds host limit
                file_size = folder_path.stat().st_size
                host_max_mb = get_file_host_setting(self.host_id, 'max_file_size_mb', 'int') or 0
                host_max_bytes = host_max_mb * 1024 * 1024 if host_max_mb > 0 else 0

                if host_max_bytes > 0 and file_size > host_max_bytes:
                    # File exceeds host limit — need to archive and split
                    self._log(
                        f"File {folder_path.name} ({file_size // (1024*1024)}MB) exceeds "
                        f"host limit ({host_max_mb}MB), archiving with split",
                        level="info"
                    )
                    archive_paths = self._get_or_create_archive(
                        db_id=db_id,
                        folder_path=folder_path,
                        gallery_name=gallery_name,
                        archive_format='zip',
                        compression='store',
                        split_size_mb=host_max_mb,
                    )
                    archive_created = True
                else:
                    # Upload raw file directly
                    archive_paths = [folder_path]
            else:
                # Directory: archive as before
                defaults = load_user_defaults()
                archive_format = defaults.get('archive_format', 'zip')
                archive_compression = defaults.get('archive_compression', 'store')
                split_enabled = defaults.get('archive_split_enabled', False)
                split_mode = defaults.get('archive_split_mode', 'fixed')

                if not split_enabled:
                    split_size_mb = 0
                elif split_mode == 'auto_host_limit':
                    host_max_mb = get_file_host_setting(self.host_id, 'max_file_size_mb', 'int') or 0
                    if host_max_mb > 0:
                        estimated_bytes = sum(
                            f.stat().st_size for f in folder_path.iterdir() if f.is_file()
                        )
                        split_size_mb = host_max_mb if estimated_bytes > host_max_mb * 1024 * 1024 else 0
                    else:
                        self._log(
                            "Split mode is 'only when exceeding host limit' but no max file size "
                            "is configured for this host — skipping split",
                            level="warning"
                        )
                        split_size_mb = 0
                else:
                    split_size_mb = defaults.get('archive_split_size_mb', 0)

                # Pre-flight disk space check before archive creation
                import shutil as _shutil
                import tempfile as _tempfile
                try:
                    temp_free = _shutil.disk_usage(_tempfile.gettempdir()).free
                    estimated_size = sum(
                        f.stat().st_size for f in folder_path.iterdir()
                        if f.is_file()
                    )
                    critical_mb = 512
                    critical_bytes = critical_mb * 1024 * 1024
                    if temp_free < estimated_size + critical_bytes:
                        free_mb = temp_free // (1024 * 1024)
                        need_mb = (estimated_size + critical_bytes) // (1024 * 1024)
                        raise OSError(
                            f"Insufficient disk space for archive: "
                            f"{free_mb}MB free, need ~{need_mb}MB"
                        )
                except OSError:
                    raise
                except Exception as e:
                    self._log(f"Disk space pre-flight check failed: {e}", level="warning")

                archive_paths = self._get_or_create_archive(
                    db_id=db_id,
                    folder_path=folder_path,
                    gallery_name=gallery_name,
                    archive_format=archive_format,
                    compression=archive_compression,
                    split_size_mb=split_size_mb,
                )
                archive_created = True

            # Step 2: Create client (reuses session if available)
            client = self._create_client(host_config)

            def on_progress(uploaded: int, total: int, speed_bps: float = 0.0):
                """Progress callback from pycurl with speed tracking."""
                try:
                    # Throttle progress signal emissions to max 4 per second using instance-level state
                    current_time = time.time()
                    upload_key = (db_id, host_name)

                    should_emit = False
                    with self._throttle_lock:
                        state = self._upload_throttle_state.setdefault(upload_key, {
                            'last_emit': 0,
                            'last_progress': (0, 0)
                        })

                        time_elapsed = current_time - state['last_emit']
                        if time_elapsed >= 0.25:  # Max 4 per second
                            last_progress = state['last_progress']
                            # Emit if progress changed or it's been >0.5s (prevent frozen UI)
                            if (uploaded, total) != last_progress or time_elapsed >= 0.5:
                                should_emit = True
                                state['last_emit'] = current_time
                                state['last_progress'] = (uploaded, total)

                    # Emit outside the lock to avoid deadlocks
                    if should_emit:
                        self.upload_progress.emit(db_id, host_name, uploaded, total, speed_bps)

                    # Emit bandwidth periodically (speed_bps is bytes/sec, convert to KB/s)
                    # Only emit when we have actual speed data - don't emit 0 during
                    # connection setup, SSL handshake, or server response wait
                    if speed_bps > 0:
                        kbps = speed_bps / 1024.0
                        self._emit_bandwidth_immediate(kbps)
                except Exception as e:
                    self._log(f"Progress callback error: {e}\n{traceback.format_exc()}", level="error")
                    self._cleanup_upload_throttle_state(db_id, host_name)
                    # Continue upload - don't abort on display errors

            def should_stop():
                """Check if upload should be cancelled."""
                return self._should_stop_current or self._stop_event.is_set()

            # For K2S-family siblings: look up the primary's server-side md5 from
            # the DB once, keyed by part_number. We pass it to upload_file so the
            # client can probe createFileByHash before doing any real upload. The
            # primary stores its server md5 via _fetch_server_md5 after its own
            # upload completes, so by the time we get here (coordinator unblocked
            # us on primary settle) it's already written.
            sibling_md5_by_part: Dict[int, str] = {}
            family = get_host_family(host_name) if is_family_dedup_enabled() else None
            if family:
                try:
                    all_parts = self.queue_store.get_family_completed_parts(db_id, family)
                    for p in all_parts:
                        if p["host_name"] == host_name:
                            continue
                        pn = p["part_number"]
                        md5 = p["md5_hash"]
                        if md5 and pn not in sibling_md5_by_part:
                            sibling_md5_by_part[pn] = md5
                    if sibling_md5_by_part:
                        self._log(
                            f"Family sibling md5s available for {host_name}: "
                            f"{len(sibling_md5_by_part)} part(s)",
                            level="info",
                        )
                    else:
                        self._log(
                            f"No sibling md5s in DB for {host_name} gallery_fk={db_id} "
                            f"family={family} — will upload normally",
                            level="debug",
                        )
                except Exception as e:
                    self._log(
                        f"Failed to look up sibling md5s for {host_name}: {e}",
                        level="warning",
                    )

            # Upload each archive part
            for part_idx, archive_path in enumerate(archive_paths):
                if should_stop():
                    break

                part_size = archive_path.stat().st_size

                # For first part (part_idx=0), use the existing upload_id
                # For additional parts, create new file_host_upload rows
                if part_idx == 0:
                    current_upload_id = upload_id
                    self.queue_store.update_file_host_upload(
                        current_upload_id,
                        zip_path=str(archive_path),
                        total_bytes=part_size
                    )
                else:
                    current_upload_id = self.queue_store.add_file_host_upload(
                        gallery_path=gallery_path,
                        host_name=host_name,
                        status='uploading',
                        part_number=part_idx
                    )
                    if not current_upload_id:
                        raise RuntimeError(
                            f"Failed to create upload record for part {part_idx + 1}"
                        )
                    self.queue_store.update_file_host_upload(
                        current_upload_id,
                        zip_path=str(archive_path),
                        total_bytes=part_size,
                        started_ts=int(time.time())
                    )

                if len(archive_paths) > 1:
                    self._log(
                        f"Uploading part {part_idx + 1}/{len(archive_paths)} "
                        f"({part_size / (1024*1024):.1f} MB): {archive_path.name}",
                        level="info")

                # Persist file size before upload. MD5 handling:
                #   - Hosts that embed the md5 in their init request (e.g.
                #     RapidGator, require_file_hash=True) compute it locally.
                #   - K2S-family siblings pass the primary's server-side md5
                #     (fetched from the DB above) — the client uses it to probe
                #     createFileByHash before uploading.
                file_size = archive_path.stat().st_size
                md5_hash: Optional[str] = None
                if host_config.require_file_hash:
                    md5_hash = self._compute_md5(archive_path)
                    self.queue_store.update_file_host_upload(
                        current_upload_id,
                        md5_hash=md5_hash,
                        file_size=file_size,
                    )
                else:
                    md5_hash = sibling_md5_by_part.get(part_idx)
                    self.queue_store.update_file_host_upload(
                        current_upload_id,
                        file_size=file_size,
                    )

                # Reset upload timing just before actual transfer
                upload_start_time = time.time()

                # Perform upload for this part
                result = client.upload_file(
                    file_path=archive_path,
                    on_progress=on_progress,
                    should_stop=should_stop,
                    md5_hash=md5_hash
                )

                # Calculate transfer time for metrics
                upload_elapsed_time = time.time() - upload_start_time

                # Handle result for this part
                if result.get('status') == 'success':
                    download_url = result.get('url', '')
                    file_id = result.get('upload_id') or result.get('file_id', '')
                    # For K2S-family hosts, the client fetched the authoritative
                    # server-side MD5 after upload. Overwrite the pre-upload local
                    # md5 with it so sibling dedup probes hit the backend hash table.
                    server_md5 = result.get('server_md5')

                    # Update database with success for this part
                    if current_upload_id:
                        update_kwargs = dict(
                            status='completed',
                            finished_ts=int(time.time()),
                            download_url=download_url,
                            file_id=file_id,
                            file_name=archive_path.name,
                            raw_response=str(result.get('raw_response', {}))[:10000],
                            uploaded_bytes=part_size,
                        )
                        if server_md5:
                            update_kwargs['md5_hash'] = server_md5
                        self.queue_store.update_file_host_upload(
                            current_upload_id,
                            **update_kwargs,
                        )

                    # Mark deduplication status
                    if result.get('deduplication') and current_upload_id:
                        self.queue_store.update_file_host_upload(
                            current_upload_id,
                            deduped=1
                        )

                    # Record metrics for successful transfer
                    from src.utils.metrics_store import get_metrics_store
                    metrics_store = get_metrics_store()
                    if metrics_store:
                        try:
                            peak_kbps = self.queue_store._main_window.worker_signal_handler.bandwidth_manager.get_file_host_bandwidth(host_name)
                        except AttributeError:
                            peak_kbps = None
                        metrics_store.record_transfer(
                            host_name=self.host_id,
                            bytes_uploaded=part_size,
                            transfer_time=upload_elapsed_time,
                            success=True,
                            observed_peak_kbps=peak_kbps,
                            deduped=bool(result.get('deduplication'))
                        )
                    avg_speed_mbs = (part_size / upload_elapsed_time / (1024 * 1024)) if upload_elapsed_time > 0 else 0
                    self._log(
                        f"Successfully uploaded {gallery_name}"
                        f"{f' (part {part_idx + 1})' if len(archive_paths) > 1 else ''}"
                        f" in {upload_elapsed_time:.1f}s ({avg_speed_mbs:.1f} MiB/s): {download_url}",
                        level="info")

                    # Log raw server response for debugging
                    raw_resp = result.get('raw_response', {})
                    if raw_resp:
                        resp_str = json.dumps(raw_resp, ensure_ascii=False).replace('\n', '\\n')
                        self._log(f"Server response: {resp_str}", level="debug")

                    # Update session after successful upload (in case tokens refreshed)
                    self._update_session_from_client(client)

                else:
                    raise Exception(result.get('error', f'Upload failed for part {part_idx + 1}'))

            # All parts uploaded successfully
            # CRITICAL: Emit signal FIRST before any blocking operations
            self.upload_completed.emit(db_id, host_name, result)
            self._cleanup_upload_throttle_state(db_id, host_name)
            self.coordinator.record_completion(success=True)

        except Exception as e:
            error_msg = str(e)
            self._log(
                f"Upload failed for gallery {db_id}: {error_msg}",
                level="error")

            # Get current retry count
            uploads = self.queue_store.get_file_host_uploads(gallery_path)
            current_upload = next((u for u in uploads if u['id'] == upload_id), None)
            retry_count = current_upload['retry_count'] if current_upload else 0

            # Check if we should retry
            auto_retry = get_file_host_setting(host_name, "auto_retry", "bool")
            max_retries = get_file_host_setting(host_name, "max_retries", "int")

            # Check if error is retryable (don't retry folder/permission errors)
            is_retryable = self._is_retryable_error(e, error_msg)

            should_retry = (
                auto_retry and
                retry_count < max_retries and
                not self._should_stop_current and
                is_retryable  # Only retry if error is recoverable
            )

            if should_retry:
                self._cleanup_upload_throttle_state(db_id, host_name)  # ADD THIS LINE
                # Increment retry count and set back to pending
                self.queue_store.update_file_host_upload(
                    upload_id,
                    status='pending',
                    error_message=error_msg,
                    retry_count=retry_count + 1
                )

                self._log(
                    f"Retrying upload '{gallery_name}' (attempt {retry_count + 1}/{max_retries})",
                    level="info"
                )
            else:
                # CRITICAL: Emit failed signal FIRST before blocking operations
                # This ensures GUI gets immediate notification
                self.upload_failed.emit(db_id, host_name, error_msg)

                self._cleanup_upload_throttle_state(db_id, host_name)

                # Mark as failed (AFTER signal emission)
                self.queue_store.update_file_host_upload(
                    upload_id,
                    status='failed',
                    finished_ts=int(time.time()),
                    error_message=error_msg
                )

                # Record failure (fast operation)
                self.coordinator.record_completion(success=False)

                # Record metrics for failed transfer (async via queue)
                from src.utils.metrics_store import get_metrics_store
                metrics_store = get_metrics_store()
                if metrics_store:
                    # Calculate elapsed time from upload start
                    elapsed = time.time() - upload_start_time
                    metrics_store.record_transfer(
                        host_name=self.host_id,
                        bytes_uploaded=0,  # Failed uploads don't count bytes
                        transfer_time=elapsed,
                        success=False,
                        observed_peak_kbps=None  # No peak tracking for failed uploads
                    )

        finally:
            # Release ZIP reference only if an archive was actually created
            if archive_created:
                self.archive_manager.release_archive(db_id)

            # Clear current upload tracking
            self.current_upload_id = None
            self.current_host = None
            self.current_db_id = None
            self._should_stop_current = False

    def _try_family_mirror(self, row: dict, client, family) -> bool:
        """Attempt to mirror a family primary's completed part set via hash dedup.

        Reads SIBLING primary's completed part rows from the DB (excluding the
        calling worker's own host), calls client.try_create_by_hash for each,
        and — only if every part mirrors successfully — creates/updates mirror
        rows. All DB writes are deferred until the full loop succeeds, so a
        partial mirror failure leaves the DB untouched and the head row remains
        `pending` for the caller to retry via full upload.

        Retries with exponential backoff if the initial attempt misses, to allow
        time for backend propagation across family hosts. Retry count and base
        delay are configurable in Advanced settings (k2s_dedup/retry_attempts
        and k2s_dedup/retry_base_delay_sec).

        Returns True only if every sibling part mirrored successfully. Returns
        False on any miss after all retries, empty sibling set, or exception —
        caller should fall through to the full-upload flow.

        Args:
            row: The pending row currently being processed. Must contain 'id',
                'gallery_fk', 'host_name', and 'gallery_path'.
            client: The FileHostClient instance for this worker's host.
            family: The backend_family name, or None if the host has no family.

        Returns:
            True if all sibling parts deduped; False otherwise.
        """
        if not family:
            return False

        host_name = row["host_name"]
        all_parts = self.queue_store.get_family_completed_parts(
            row["gallery_fk"], family
        )
        # Filter out self — we only mirror SIBLING parts, not our own.
        sibling_parts = [p for p in all_parts if p["host_name"] != host_name]
        if not sibling_parts:
            return False

        gallery_path = row.get("gallery_path")
        head_upload_id = row["id"]

        from src.core.file_host_config import get_dedup_retry_settings
        max_retries, base_delay = get_dedup_retry_settings()

        part_results: list = []  # list of (part_number, md5, file_name, result)

        for attempt in range(max_retries + 1):  # attempt 0 = immediate, then retries
            if self._should_stop_current or self._stop_event.is_set():
                return False

            if attempt > 0:
                delay = base_delay * (2 ** (attempt - 1))
                self._log(
                    f"Family dedup: waiting for sibling MD5, retry in {delay}s "
                    f"(attempt {attempt}/{max_retries})",
                    level="info",
                )
                # Sleep in 1-second chunks so stop events are honoured promptly
                # and emit countdown for the worker status display
                for remaining in range(delay, 0, -1):
                    if self._should_stop_current or self._stop_event.is_set():
                        return False
                    self.status_updated.emit(
                        self.host_id,
                        f"Waiting for sibling MD5... {remaining}s"
                    )
                    time.sleep(1)

            # Phase 1: attempt every dedup call and collect results WITHOUT
            # touching the DB. Only if every part succeeds do we commit.
            part_results = []
            all_succeeded = True
            try:
                for part in sibling_parts:
                    part_number = part["part_number"]
                    md5 = part["md5_hash"]
                    file_name = part["file_name"] or ""
                    sibling_host = part["host_name"]
                    sibling_file_id = part.get("file_id") or ""

                    # Re-fetch MD5 from the primary host's API if not yet available
                    if not md5 and sibling_file_id:
                        self._log(
                            f"MD5 not yet available for {sibling_host} file {sibling_file_id}, "
                            f"re-fetching from API",
                            level="info",
                        )
                        md5 = FileHostClient.fetch_md5_for_host(
                            sibling_host, sibling_file_id, self._log
                        )
                        if md5:
                            # Store it in the DB so future attempts don't need to re-fetch
                            self.queue_store.update_file_host_upload(
                                part["id"], md5_hash=md5
                            )
                            self._log(
                                f"Got MD5 from {sibling_host}: {md5}",
                                level="info",
                            )
                        else:
                            self._log(
                                f"MD5 still not available from {sibling_host} for "
                                f"file {sibling_file_id}",
                                level="info",
                            )
                            all_succeeded = False
                            break

                    if not md5:
                        all_succeeded = False
                        break

                    result = client.try_create_by_hash(md5, file_name)
                    if not (result and result.get("status") == "success"):
                        all_succeeded = False
                        break
                    part_results.append((part_number, md5, file_name, result))
            except Exception as e:
                self._log(
                    f"Family mirror exception on attempt {attempt} for {host_name} "
                    f"gallery_path={gallery_path}: {e}",
                    level="warning",
                )
                all_succeeded = False

            if all_succeeded:
                break  # proceed to phase 2 commit
        else:
            # Exhausted all attempts
            self._log(
                f"Family dedup exhausted {max_retries} retries for {host_name} "
                f"gallery_path={gallery_path}, falling through to full upload",
                level="info",
            )
            return False

        if not part_results:
            return False

        # Phase 2: commit. Process secondaries first, then the head row last
        # so a mid-phase failure leaves the head row pending for retry.
        try:
            # Process part_number > 0 first, collect head row update for last
            head_result = None
            for part_number, md5, file_name, result in part_results:
                if part_number == 0:
                    head_result = (md5, file_name, result)
                    continue
                new_id = self.queue_store.add_file_host_upload(
                    gallery_path=gallery_path,
                    host_name=host_name,
                    status="pending",
                    part_number=part_number,
                    dedup_only=1,
                )
                if new_id is None:
                    self._log(
                        f"Family mirror: failed to create mirror row for "
                        f"{host_name} part {part_number}",
                        level="warning",
                    )
                    return False
                self.queue_store.update_file_host_upload(
                    new_id,
                    status="completed",
                    md5_hash=md5,
                    file_name=file_name,
                    download_url=result.get("url", ""),
                    file_id=result.get("file_id", ""),
                    deduped=1,
                    finished_ts=int(time.time()),
                )
            # Now update the head row (part 0). This is the last write — if
            # earlier writes failed we already returned False.
            if head_result is not None:
                md5, file_name, result = head_result
                self.queue_store.update_file_host_upload(
                    head_upload_id,
                    status="completed",
                    md5_hash=md5,
                    file_name=file_name,
                    download_url=result.get("url", ""),
                    file_id=result.get("file_id", ""),
                    deduped=1,
                    finished_ts=int(time.time()),
                )
            # Record dedup stats — bytes_saved (not bytes_uploaded) since
            # no actual transfer occurred, just a createFileByHash API call
            from src.utils.metrics_store import get_metrics_store
            metrics_store = get_metrics_store()
            if metrics_store:
                total_bytes = sum(p.get("total_bytes", 0) for p in sibling_parts)
                metrics_store.record_transfer(
                    host_name=self.host_id,
                    bytes_uploaded=0,
                    transfer_time=0.001,
                    success=True,
                    files_count=len(part_results),
                    deduped=True,
                    bytes_saved=total_bytes,
                )

            return True
        except Exception as e:
            self._log(
                f"Family mirror commit phase failed for {host_name} "
                f"gallery_path={gallery_path}: {e}",
                level="warning",
            )
            return False

    def _emit_bandwidth(self):
        """Calculate and emit current bandwidth."""
        now = time.time()

        # Only emit every 0.5 seconds
        if now - self._bw_last_emit < 0.5:
            return

        elapsed = now - self._bw_last_time
        if elapsed > 0:
            current_bytes = self.bandwidth_counter.get()
            bytes_transferred = current_bytes - self._bw_last_bytes

            # Calculate KB/s
            kbps = (bytes_transferred / 1024.0) / elapsed

            # Emit signal
            self.bandwidth_updated.emit(self.host_id, kbps)

            # Update tracking
            self._bw_last_bytes = current_bytes
            self._bw_last_time = now
            self._bw_last_emit = now

    def _emit_bandwidth_immediate(self, kbps: float):
        """Emit bandwidth immediately without throttling (for pycurl-calculated speeds)."""
        now = time.time()

        # Still throttle to 0.5 seconds to avoid GUI overload
        if now - self._bw_last_emit < 0.5:
            return

        # Emit the speed directly (already calculated by pycurl callback)
        self.bandwidth_updated.emit(self.host_id, kbps)

        # Update tracking
        self._bw_last_emit = now

    def get_current_upload_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current upload.

        Returns:
            Dictionary with current upload info, or None
        """
        if self.current_upload_id is None:
            return None

        return {
            'upload_id': self.current_upload_id,
            'db_id': self.current_db_id,
            'host_name': self.current_host
        }

    # =========================================================================
    # Storage and Testing Methods (bypass coordinator, for UI operations)
    # =========================================================================

    def check_storage(self) -> None:
        """Check storage from cache (30min TTL) or fetch from server.

        Emits storage_updated signal with results.
        Uses QSettings cache to avoid unnecessary API calls.
        """
        # Step 0: Check if host even supports storage info
        host_config = self.config_manager.get_host(self.host_id)
        if not host_config or not host_config.user_info_url:
            # Host doesn't have storage tracking - skip silently
            return

        # Step 1: Check cache first
        cache = self._load_storage_cache()
        if cache:
            age = int(time.time()) - cache['timestamp']
            if age < 1800:  # 30 minutes TTL
                # Cache valid - emit immediately
                self._log(
                    f"Using cached storage (age: {age}s)",
                    level="debug"
                )
                self.storage_updated.emit(self.host_id, cache['total'], cache['left'])
                return

        # Step 2: Cache invalid/missing - fetch from server
        self._log(
            "Fetching storage from server",
            level="debug"
        )

        try:
            host_config = self.config_manager.get_host(self.host_id)
            if not host_config:
                raise Exception(f"Host config not found: {self.host_id}")

            # Create client (reuses session if available)
            client = self._create_client(host_config)

            # Check if storage was cached during login (saves an API call!)
            cached_storage = client.get_cached_storage_from_login()
            if cached_storage and cached_storage.get('storage_total') and cached_storage.get('storage_left'):
                self._log(f"Cached storage from login: {json.dumps(cached_storage, indent=2).replace(chr(10), '\n')}", level="trace")

                total = int(cached_storage.get('storage_total') or 0)
                left = int(cached_storage.get('storage_left') or 0)
                self._log(
                    f"Got storage from login response for {self.host_id} (no /info call needed!)",
                    level="trace"
                )
            else:
                # No storage in login - make separate /info call
                user_info = client.get_user_info()

                user_info_formatted = json.dumps(user_info, indent=2).replace(chr(10), '\n') if user_info else "None"
                self._log(f"Fetched from /info call: {user_info_formatted}", level="trace")

                total_raw = user_info.get('storage_total')
                left_raw = user_info.get('storage_left')

                self._log(
                    f"Extracted storage_total={total_raw}, storage_left={left_raw}",
                    level="trace"
                )

                # Validate before emitting - DO NOT overwrite good data with bad data
                if total_raw is None or left_raw is None or total_raw <= 0 or left_raw < 0:
                    self._log(
                        f"Invalid storage data from API (total={total_raw}, left={left_raw}) - keeping cached data",
                        level="debug"
                    )
                    return  # Do NOT emit signal, do NOT save to cache

                # Convert to int only after validation
                total = int(total_raw)
                left = int(left_raw)

            # Step 3: Save to cache (only if we have valid data)
            self._save_storage_cache(total, left)

            # Step 4: Emit signal (only if we have valid data)
            self.storage_updated.emit(self.host_id, total, left)

            self._log(
                f"Storage updated: {left}/{total} bytes free",
                level="info")

            # Update session after storage check (in case tokens refreshed)
            self._update_session_from_client(client)

        except Exception as e:
            self._log(
                f"Storage check failed: {e}",
                level="debug")
            # Do NOT emit signal with bad data

    @pyqtSlot()
    def test_connection(self) -> None:
        """Run full test suite: credentials → user_info → upload → delete.

        Emits test_completed signal with results dict.
        Bypasses coordinator - this is a UI test operation.
        """
        self._log(
            "Starting connection test",
            level="info")

        results = {
            'timestamp': int(time.time()),
            'credentials_valid': False,
            'user_info_valid': False,
            'upload_success': False,
            'delete_success': False,
            'error_message': ''
        }

        try:
            host_config = self.config_manager.get_host(self.host_id)
            if not host_config:
                raise Exception(f"Host config not found: {self.host_id}")

            # Create client (reuses session if available)
            client = self._create_client(host_config)

            # Test 1: Credentials
            #self._log("Testing credentials...", level="debug")
            cred_result = client.test_credentials()

            if not cred_result.get('success'):
                results['error_message'] = cred_result.get('message', 'Credential test failed')
                self._save_test_results(results)
                self.test_completed.emit(self.host_id, results)
                self._log("Test #1: FAIL - Unable authenticate using credentials", level="warning")
                return

            results['credentials_valid'] = True
            results['user_info_valid'] = bool(cred_result.get('user_info'))
            self._log("Test #1: PASS - Authenticated successfully using credentials", level="debug")

            # Cache storage info if available (opportunistic caching during test)
            user_info = cred_result.get('user_info', {})
            if not user_info:
                self._log("Test #2: FAIL - Unable to get user info", level="debug")
            else:
                self._log("Test #2: PASS - Successfully fetched user info", level="debug")
            # Format user_info for log viewer (with escaped newlines for expansion)

            user_info_formatted = json.dumps(user_info, indent=2).replace(chr(10), '\\n') if user_info else "None"
            self._log(f"user_info from test: {user_info_formatted}", level="debug")

            if user_info:
                storage_total = user_info.get('storage_total')
                storage_left = user_info.get('storage_left')
                self._log(
                    f"Extracted storage values:"
                    f" storage_total = {storage_total}"
                    f" ({type(storage_total).__name__}) "
                    f" storage_left = {storage_left}"
                    f" ({type(storage_left).__name__})",
                    level="debug"
                )
                if storage_total is not None and storage_left is not None:
                    try:
                        total = int(storage_total or 0)
                        left = int(storage_left or 0)
                        self._save_storage_cache(total, left)
                        self.storage_updated.emit(self.host_id, total, left)
                        self._log(f"Cached storage during test: {left}/{total} bytes", level="trace")
                    except (ValueError, TypeError) as e:
                        self._log(f"Failed to parse storage during test: {e}", level="error")
                else:
                    self._log(
                        f"Storage data missing in test response (total={storage_total}, left={storage_left})",
                        level="debug"
                    )
            else:
                self._log("No user_info in test credentials response", level="debug")

            # Test 2: Upload
            #self._log("(Test 3/4): Testing upload functionality...", level="debug")
            upload_result = client.test_upload(cleanup=False)

            if not upload_result.get('success'):
                results['error_message'] = upload_result.get('message', 'Upload test failed')
                self._save_test_results(results)
                self.test_completed.emit(self.host_id, results)
                self._log("Test #3: FAIL - failed to upload test file", level="warning")
                return

            results['upload_success'] = True
            self._log("Test #3: PASS - uploaded test file successfully", level="info")
            # Test 3: Delete (if host supports it)
            file_id = upload_result.get('file_id') or upload_result.get('upload_id')
            if file_id and host_config.delete_url:
                try:
                    #self._log("(Test 4/4): Testing delete functionality...", level="debug")
                    client.delete_file(file_id)
                    results['delete_success'] = True
                    self._log("Test #4: PASS - deleted test file successfully", level="info")
                except Exception as e:
                    self._log(f"Test #4: FAIL - failed to delete test file: {e}", level="error")
                    # Don't fail entire test if delete fails
                    results['delete_success'] = False

            # All tests passed (or delete not supported)
            self._save_test_results(results)

            # Update session after test completes (in case tokens refreshed)
            self._update_session_from_client(client)

            self.test_completed.emit(self.host_id, results)

            passed_count = sum([
                1 if results['credentials_valid'] else 0,
                1 if results['user_info_valid'] else 0,
                1 if results['upload_success'] else 0,
                1 if results['delete_success'] else 0
            ])
            self._log(
                f"Tests completed: {passed_count}/4 tests passed",
                level="info"
            )

        except Exception as e:
            results['error_message'] = str(e)
            self._save_test_results(results)
            self.test_completed.emit(self.host_id, results)

            self._log(
                f"Connection test failed: {e}",
                level="warning")

    # =========================================================================
    # Cache Helper Methods
    # =========================================================================

    def _load_storage_cache(self) -> Optional[Dict[str, Any]]:
        """Load storage cache from QSettings.

        Returns:
            Cache dict with timestamp, total, left, or None if no cache
        """
        ts = self.settings.value(f"FileHosts/{self.host_id}/storage_ts", None, type=int)
        if not ts or ts == 0:
            return None

        # Use str type and manual conversion to avoid Qt's 32-bit int overflow
        total_str = self.settings.value(f"FileHosts/{self.host_id}/storage_total", "0")
        left_str = self.settings.value(f"FileHosts/{self.host_id}/storage_left", "0")

        return {
            'timestamp': ts,
            'total': int(total_str) if total_str else 0,
            'left': int(left_str) if left_str else 0
        }

    def _save_storage_cache(self, total: int, left: int) -> None:
        """Save storage cache to QSettings.

        Storage values are saved as strings to avoid Qt's 32-bit int overflow
        on some platforms. Always load with manual int() conversion.

        Args:
            total: Total storage in bytes
            left: Free storage in bytes
        """
        self.settings.setValue(f"FileHosts/{self.host_id}/storage_ts", int(time.time()))
        self.settings.setValue(f"FileHosts/{self.host_id}/storage_total", str(total))
        self.settings.setValue(f"FileHosts/{self.host_id}/storage_left", str(left))
        pass  # Storage cache saved
        self.settings.sync()

    def _save_test_results(self, results: Dict[str, Any]) -> None:
        """Save test results to QSettings.

        Args:
            results: Test results dictionary
        """
        prefix = f"FileHosts/TestResults/{self.host_id}"
        self.settings.setValue(f"{prefix}/timestamp", results['timestamp'])
        self.settings.setValue(f"{prefix}/credentials_valid", results['credentials_valid'])
        self.settings.setValue(f"{prefix}/user_info_valid", results['user_info_valid'])
        self.settings.setValue(f"{prefix}/upload_success", results['upload_success'])
        self.settings.setValue(f"{prefix}/delete_success", results['delete_success'])
        self.settings.setValue(f"{prefix}/error_message", results['error_message'])
        self.settings.sync()

    def load_test_results(self) -> Optional[Dict[str, Any]]:
        """Load test results from QSettings.

        Returns:
            Test results dict with timestamp and test outcomes, or None if no results
        """
        prefix = f"FileHosts/TestResults/{self.host_id}"
        ts = self.settings.value(f"{prefix}/timestamp", None, type=int)
        if not ts or ts == 0:
            return None

        return {
            'timestamp': ts,
            'credentials_valid': self.settings.value(f"{prefix}/credentials_valid", False, type=bool),
            'user_info_valid': self.settings.value(f"{prefix}/user_info_valid", False, type=bool),
            'upload_success': self.settings.value(f"{prefix}/upload_success", False, type=bool),
            'delete_success': self.settings.value(f"{prefix}/delete_success", False, type=bool),
            'error_message': self.settings.value(f"{prefix}/error_message", '', type=str)
        }
