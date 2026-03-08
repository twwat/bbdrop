"""
IMX.to image host uploader.

Extracted from bbdrop.py — contains the IMX.to API client (ImxToUploader)
and supporting helper classes (NestedProgressBar, UploadProgressWrapper,
ProgressEstimator).
"""

import io
import os
import re
import json
import sys
import time
import threading
import mimetypes
from datetime import datetime
from typing import Optional, Any
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

import requests
from requests.adapters import HTTPAdapter
import pycurl
import certifi
from tqdm import tqdm

from src.utils.format_utils import format_binary_size
from src.utils.logger import log
from src.network.image_host_client import ImageHostClient
from src.core.image_host_config import (
    get_image_host_config_manager,
    get_image_host_setting,
    ImageHostConfig,
)
from src.proxy.pycurl_adapter import PyCurlProxyAdapter


class NestedProgressBar:
    """Custom progress bar with nested levels for better upload tracking"""

    def __init__(self, total, desc, level=0, parent=None):
        self.total = total
        self.desc = desc
        self.level = level
        self.parent = parent
        self.current = 0
        self.pbar = None
        self.children = []

    def __enter__(self):
        indent = "  " * self.level
        self.pbar = tqdm(
            total=self.total,
            desc=f"{indent}{self.desc}",
            unit="img",
            leave=False,
            position=self.level
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.pbar:
            self.pbar.close()

    def update(self, n=1):
        self.current += n
        if self.pbar:
            self.pbar.update(n)

    def set_postfix_str(self, text):
        if self.pbar:
            self.pbar.set_postfix_str(text)

    def add_child(self, child):
        self.children.append(child)
        child.parent = self


class UploadProgressWrapper:
    """File-like wrapper that tracks bytes during network transmission.

    When requests.post() uploads multipart form data, it calls read() on this
    wrapper repeatedly during HTTP transmission. This allows accurate tracking
    of actual network bytes sent (not disk reads).
    """

    def __init__(self, file_data: bytes, callback=None):
        """Initialize wrapper with file data and optional progress callback.

        Args:
            file_data: Raw bytes to upload
            callback: Optional callable(bytes_sent, total_bytes) invoked on each read()
        """
        self._bytesio = io.BytesIO(file_data)
        self.callback = callback
        self.total_size = len(file_data)

    def read(self, size=-1):
        """Read chunk from buffer and invoke callback. Called by requests during upload."""
        chunk = self._bytesio.read(size)
        if chunk and self.callback:
            try:
                # Report cumulative bytes sent
                self.callback(self._bytesio.tell(), self.total_size)
            except Exception:
                pass  # Silently ignore callback failures
        return chunk

    def __len__(self):
        """Return total size for Content-Length header."""
        return self.total_size

    def seek(self, offset, whence=0):
        """Seek to position (required for retry logic)."""
        return self._bytesio.seek(offset, whence)

    def tell(self):
        """Return current position."""
        return self._bytesio.tell()

    def __getattr__(self, name):
        """Proxy any missing attributes to underlying BytesIO."""
        return getattr(self._bytesio, name)


class ProgressEstimator:
    """Estimates upload progress during network transmission using a background thread."""

    def __init__(self, file_size, callback):
        self.file_size = file_size
        self.callback = callback
        self.start_time = time.time()
        self.stop_flag = False
        self.thread = None

    def start(self):
        """Start progress estimation thread."""
        self.stop_flag = False
        self.thread = threading.Thread(target=self._estimate_progress, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop progress estimation thread."""
        self.stop_flag = True
        if self.thread:
            self.thread.join(timeout=0.5)

    def _estimate_progress(self):
        """Estimate upload progress based on typical upload speed."""
        # Assume 2 MB/s average upload speed for estimation
        estimated_speed_bps = 2 * 1024 * 1024  #  2 MB/s

        while not self.stop_flag:
            elapsed = time.time() - self.start_time
            estimated_bytes = min(int(elapsed * estimated_speed_bps), self.file_size)

            if self.callback:
                try:
                    self.callback(estimated_bytes, self.file_size)
                except Exception:
                    pass

            if estimated_bytes >= self.file_size:
                break

            time.sleep(0.1)  # Update every 100ms


class ImxToUploader(ImageHostClient):
    # Type hints for attributes set externally by GUI worker threads
    worker_thread: Optional[Any] = None  # Set by UploadWorker when used in GUI mode

    def _get_credentials(self):
        """Get credentials from stored config (username/password or API key)"""
        from src.utils.credentials import get_credential, decrypt_password
        # Read from QSettings (Registry) - migration happens at app startup
        username = get_credential('username')
        encrypted_password = get_credential('password')
        encrypted_api_key = get_credential('api_key')

        # Decrypt if they exist
        password = decrypt_password(encrypted_password) if encrypted_password else None
        api_key = decrypt_password(encrypted_api_key) if encrypted_api_key else None

        # Return what we have
        if username and password:
            return username, password, api_key
        elif api_key:
            return None, None, api_key

        return None, None, None

    def _setup_resilient_session(self, parallel_batch_size=4):
        """Create a session with connection pooling (no automatic retries to avoid timeout conflicts)"""
        # Configure connection pooling - use at least parallel_batch_size connections
        pool_size = max(10, parallel_batch_size)
        adapter = HTTPAdapter(
            pool_connections=pool_size,  # Number of connection pools to cache
            pool_maxsize=pool_size       # Max connections per pool
        )

        # Create session and mount adapters
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def refresh_session_pool(self):
        """Refresh session connection pool with current parallel_batch_size setting"""
        from src.utils.paths import load_user_defaults
        try:
            defaults = load_user_defaults()
            current_batch_size = defaults.get('parallel_batch_size', 4)

            # Recreate session with updated pool size
            old_cookies = self.session.cookies if hasattr(self, 'session') else None
            self.session = self._setup_resilient_session(current_batch_size)
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'DNT': '1'
            })

            # Preserve cookies from old session
            if old_cookies:
                self.session.cookies.update(old_cookies)

        except Exception as e:
            log(f"Failed to refresh session pool: {e}", level="warning", category="network")

    def __init__(self, proxy=None):
        # Initialize image host config (ABC parent)
        _cfg = get_image_host_config_manager().get_host('imx')
        if _cfg is None:
            # Fallback: create minimal config if JSON not loaded
            _cfg = ImageHostConfig(name="IMX.to", host_id="imx")
        super().__init__(_cfg, proxy=proxy)

        # Get credentials from stored config
        self.username, self.password, self.api_key = self._get_credentials()

        # Fallback to environment variable for API key if not in config
        #if not self.api_key:
        #    self.api_key = os.getenv('IMX_API')

        # Check if we have either username/password or API key
        has_credentials = (self.username and self.password) or self.api_key

        if not has_credentials:
            log("Failed to get credentials. Please set up credentials in the GUI or run --setup-secure first.", level="warning", category="auth")
            # Don't exit in GUI mode - let the user set credentials through the dialog
            # Only exit if running in CLI mode (when there's no way to set credentials interactively)
            is_gui_mode = os.environ.get('BBDROP_GUI_MODE') == '1'
            if not is_gui_mode:
                sys.exit(1)

        # Load timeout settings via image host config system (3-tier fallback)
        self.upload_connect_timeout = get_image_host_setting('imx', 'upload_connect_timeout', 'int')
        self.upload_read_timeout = get_image_host_setting('imx', 'upload_read_timeout', 'int')
        log(f"IMX timeouts: connect={self.upload_connect_timeout}s, read={self.upload_read_timeout}s", level="debug", category="network")

        self.base_url = "https://api.imx.to/v1"
        self._web_url = "https://imx.to"
        self.upload_url = f"{self.base_url}/upload.php"

        # Connection tracking for visibility
        self._upload_count = 0
        self._connection_info_logged = False

        # Thread-local storage for curl handles (connection reuse)
        self._curl_local = threading.local()

        # Set headers based on authentication method
        if self.api_key:
            from src.utils.paths import get_user_agent
            self.headers = {
                "X-API-Key": self.api_key,
                "User-Agent": get_user_agent()
            }
        else:
            self.headers = {}

        # Session for web interface with connection pooling
        parallel_batch_size = get_image_host_setting('imx', 'parallel_batch_size', 'int')
        self.session = self._setup_resilient_session(parallel_batch_size)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'DNT': '1'
        })

    def _get_thread_curl(self):
        """Get or create a thread-local curl handle for connection reuse.

        Each thread gets its own curl handle that persists across uploads,
        allowing TCP connection reuse for better performance.
        """
        if not hasattr(self._curl_local, 'curl'):
            # Create new curl handle for this thread
            self._curl_local.curl = pycurl.Curl()

            # CRITICAL: Thread safety for multi-threaded uploads
            # NOSIGNAL prevents signal-based timeouts which don't work in multi-threaded programs
            self._curl_local.curl.setopt(pycurl.NOSIGNAL, 1)

            # SECURITY: Enable SSL/TLS certificate verification to prevent MITM attacks
            # Uses certifi's trusted CA bundle for certificate validation
            self._curl_local.curl.setopt(pycurl.CAINFO, certifi.where())
            self._curl_local.curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            self._curl_local.curl.setopt(pycurl.SSL_VERIFYHOST, 2)

            if self.proxy:
                PyCurlProxyAdapter.configure_proxy(self._curl_local.curl, self.proxy)

            log(f"Created new curl handle for thread {threading.current_thread().name}", level="debug", category="network")
        return self._curl_local.curl

    def clear_api_cookies(self):
        """Clear pycurl cookies before starting new gallery upload.

        CRITICAL: Must be called before each new gallery to prevent PHP session
        reuse that causes multiple galleries to share the same gallery_id.

        This clears API cookies (pycurl), NOT web session cookies (requests.Session).
        """
        if hasattr(self._curl_local, 'curl'):
            curl = self._curl_local.curl
            curl.setopt(pycurl.COOKIELIST, "ALL")
            log("Cleared pycurl API cookies for new gallery", level="debug", category="uploads")

    @property
    def web_url(self) -> str:
        """Base web URL for IMX.to (implements ImageHostClient ABC)."""
        return self._web_url

    def get_default_headers(self) -> dict:
        """Return default HTTP headers for IMX.to uploads."""
        return self.headers

    def supports_gallery_rename(self) -> bool:
        """IMX.to supports renaming galleries after creation."""
        return True

    def sanitize_gallery_name(self, name: str) -> str:
        """IMX.to gallery name rules: alphanumeric, spaces, hyphens, dots, underscores, parens."""
        if not name:
            return 'untitled'
        sanitized = re.sub(r'[^a-zA-Z0-9,\.\s\-_\(\)]', '', name)
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        return sanitized or 'untitled'

    def upload_image(
        self, image_path, create_gallery=False,
        gallery_id=None, thumbnail_size=3,
        thumbnail_format=2, thread_session=None,
        progress_callback=None, gallery_name=None
    ):
        """
        Upload a single image to imx.to

        Args:
            image_path (str): Path to the image file
            create_gallery (bool): Whether to create a new gallery
            gallery_id (str): ID of existing gallery to add image to
            thumbnail_size (int): Thumbnail size (1=100x100, 2=180x180, 3=250x250, 4=300x300, 6=150x150)
            thumbnail_format (int): Thumbnail format (1=Fixed width, 2=Proportional, 3=Square, 4=Fixed height)
            thread_session (requests.Session): Optional thread-local session for concurrent uploads
            progress_callback (callable): Optional callback(bytes_sent, total_bytes) for bandwidth tracking

        Returns:
            dict: API response
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # Use thread-local session if provided, otherwise use shared session

        # Read file into memory BEFORE POST to enable true concurrent uploads
        # Keeping file handles open during network I/O causes Python's file I/O to serialize
        # the reads even though HTTP operations can be concurrent (7x performance penalty)
        file_read_start = time.time()
        with open(image_path, 'rb') as f:
            file_data = f.read()
        file_read_time = time.time() - file_read_start

        if not hasattr(self, '_first_read_logged'):
            log(f"Read {os.path.basename(image_path)} ({len(file_data)/1024/1024:.1f}MB) in {file_read_time:.3f}s", level="debug", category="fileio")
            self._first_read_logged = True

        # Use pycurl for upload with real progress tracking
        content_type = mimetypes.guess_type(image_path)[0] or 'application/octet-stream'

        try:
            self._upload_count += 1

            # Setup progress callback wrapper
            callback_count = [0]  # Mutable to track in closure

            def curl_progress_callback(download_total, downloaded, upload_total, uploaded):
                callback_count[0] += 1

                if progress_callback and upload_total > 0:
                    try:
                        progress_callback(int(uploaded), int(upload_total))
                    except Exception:
                        pass  # Silently ignore callback errors
                return 0

            # Get or create thread-local curl handle (connection reuse)
            curl = self._get_thread_curl()

            # Reset curl handle to clear previous settings (but keep connection alive)
            curl.reset()
            curl.setopt(pycurl.NOSIGNAL, 1)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            if self.proxy:
                PyCurlProxyAdapter.configure_proxy(curl, self.proxy)

            # NOTE: Cookies are cleared per-gallery (via clear_api_cookies()), NOT per-image.
            # This maintains PHP session continuity within a single gallery upload.
            # Clearing cookies here would break gallery_id association for subsequent images.

            response_buffer = io.BytesIO()

            # Set URL
            curl.setopt(pycurl.URL, self.upload_url)

            # Set headers
            headers_list = [f'{k}: {v}' for k, v in self.headers.items()]
            curl.setopt(pycurl.HTTPHEADER, headers_list)

            # Prepare multipart form data
            form_data = [
                ('image', (
                    pycurl.FORM_BUFFER, os.path.basename(image_path).replace('\u2014', '-').replace('\u2013', '-').encode('ascii', 'replace').decode('ascii'),
                    pycurl.FORM_BUFFERPTR, file_data,
                    pycurl.FORM_CONTENTTYPE, content_type
                )),
                ('format', 'all'),
                ('thumbnail_size', str(thumbnail_size)),
                ('thumbnail_format', str(thumbnail_format))
            ]

            if create_gallery:
                form_data.append(('create_gallery', 'true'))
            if gallery_id:
                form_data.append(('gallery_id', gallery_id))

            curl.setopt(pycurl.HTTPPOST, form_data)

            # Set progress tracking
            if progress_callback:
                curl.setopt(pycurl.NOPROGRESS, 0)
                curl.setopt(pycurl.XFERINFOFUNCTION, curl_progress_callback)

            # Capture response
            curl.setopt(pycurl.WRITEDATA, response_buffer)

            # Set timeouts
            curl.setopt(pycurl.CONNECTTIMEOUT, self.upload_connect_timeout)
            curl.setopt(pycurl.TIMEOUT, self.upload_read_timeout)

            # Perform upload
            curl.perform()

            # Get response
            status_code = curl.getinfo(pycurl.RESPONSE_CODE)
            # NOTE: Don't close curl handle - keep connection alive for reuse

            if status_code == 200:
                json_response = json.loads(response_buffer.getvalue())
                # IMX API natively returns {status, data: {image_url, thumb_url, gallery_id}}
                # Wrap through normalize_response() for standard contract compliance
                data = json_response.get('data', {}) if isinstance(json_response.get('data'), dict) else {}
                return self.normalize_response(
                    status=json_response.get('status', 'error'),
                    image_url=data.get('image_url', ''),
                    thumb_url=data.get('thumb_url', ''),
                    gallery_id=data.get('gallery_id'),
                    original_filename=data.get('original_filename', os.path.basename(image_path)),
                    bbcode=data.get('bbcode'),
                )
            else:
                response_text = response_buffer.getvalue().decode('utf-8', errors='replace')
                raise Exception(f"Upload failed with status code {status_code}: {response_text}")

        except pycurl.error as e:
            # pycurl error codes: 28=timeout, 7=connection failed, etc.
            error_code, error_msg = e.args if len(e.args) == 2 else (0, str(e))
            if error_code == 28:
                raise Exception(f"Upload timeout (connect={self.upload_connect_timeout}s, read={self.upload_read_timeout}s): {error_msg}")
            elif error_code == 7:
                raise Exception(f"Connection error during upload: {error_msg}")
            else:
                raise Exception(f"Network error during upload (code {error_code}): {error_msg}")

    def upload_folder(
        self, folder_path, gallery_name=None,
        thumbnail_size=3, thumbnail_format=2,
        max_retries=3, parallel_batch_size=4,
        template_name="default", queue_store=None
    ):
        """
        Upload all images in a folder as a gallery.

        Args:
            folder_path (str): Path to folder containing images
            gallery_name (str): Name for the gallery (optional)
            thumbnail_size (int): Thumbnail size setting
            thumbnail_format (int): Thumbnail format setting
            max_retries (int): Maximum retry attempts for failed uploads

        Returns:
            dict: Contains gallery URL and individual image URLs
        """
        from bbdrop import (
            check_if_gallery_exists, save_unnamed_gallery,
            build_gallery_filenames, generate_bbcode_from_template,
            save_gallery_artifacts, get_central_storage_path, timestamp,
            __version__,
        )

        start_time = time.time()

        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        # Get all image files in folder and calculate total size
        scan_start = time.time()
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif')
        image_files = []
        total_size = 0
        image_dimensions = []

        for f in os.listdir(folder_path):
            if f.lower().endswith(image_extensions) and os.path.isfile(os.path.join(folder_path, f)):
                image_files.append(f)
                file_path = os.path.join(folder_path, f)
                file_size = os.path.getsize(file_path)
                total_size += file_size

                # Get image dimensions using PIL
                try:
                    from PIL import Image
                    with Image.open(file_path) as img:
                        width, height = img.size
                        image_dimensions.append((width, height))
                except ImportError:
                    image_dimensions.append((0, 0))  # PIL not available
                except Exception:
                    image_dimensions.append((0, 0))  # Error reading image

        scan_duration = time.time() - scan_start
        log(f"File scanning and PIL processing took {scan_duration:.6f}s for {len(image_files)} files", level="debug", category="scan")

        if not image_files:
            raise ValueError(f"No image files found in {folder_path}")

        # Create gallery with name (default to folder name if not provided)
        if not gallery_name:
            gallery_name = os.path.basename(folder_path)

        # Keep original gallery name - sanitization only happens in rename worker
        original_name = gallery_name

        # Check if gallery already exists
        check_start = time.time()
        existing_files = check_if_gallery_exists(gallery_name)
        check_duration = time.time() - check_start
        log(f"Gallery existence check took {check_duration:.6f}s", level="debug", category="uploads")

        if existing_files:
            log(f"Found existing gallery files for '{gallery_name}':", level="debug", category="uploads")
            for file_path in existing_files:
                log(f"   {file_path}", level="debug", category="uploads")

            response = input(f"{timestamp()} Gallery appears to already exist. Continue anyway? (y/N): ")
            if response.lower() != 'y':
                log(f"Skipping {folder_path}", level="info", category="uploads")
                return None

        # Create gallery (skip login since it's already done). If creation fails, fall back to API-only
        create_start = time.time()
        gallery_id = self.create_gallery_with_name(gallery_name, skip_login=True)
        create_duration = time.time() - create_start
        log(f"Gallery creation took {create_duration:.6f}s", level="debug", category="uploads")
        initial_completed = 0
        initial_uploaded_size = 0
        preseed_images = []
        files_to_upload = []
        if not gallery_id:
            log("Failed to create named gallery, falling back to API-only upload...", level="warning", category="uploads")
            # Upload first image to create gallery
            first_file = image_files[0]
            first_image_path = os.path.join(folder_path, first_file)
            log(f"Uploading first image: {first_file}", level="info", category="uploads")
            first_response = self.upload_image(
                first_image_path,
                create_gallery=True,
                thumbnail_size=thumbnail_size,
                thumbnail_format=thumbnail_format
            )
            if first_response.get('status') != 'success':
                raise Exception(f"{timestamp()} Failed to create gallery: {first_response}")
            gallery_id = first_response['data'].get('gallery_id')
            # Save for later renaming (with sanitized name)
            save_unnamed_gallery(gallery_id, gallery_name)
            preseed_images = [first_response['data']]
            initial_completed = 1
            try:
                initial_uploaded_size = os.path.getsize(first_image_path)
            except Exception:
                initial_uploaded_size = 0
            files_to_upload = image_files[1:]
        else:
            files_to_upload = image_files

        gallery_url = f"https://imx.to/g/{gallery_id}"

        # Store results
        results = {
            'gallery_url': gallery_url,
            'images': list(preseed_images)
        }

        # Upload all images to the created gallery with progress bars
        def upload_single_image(image_file, attempt=1, pbar=None):
            image_path = os.path.join(folder_path, image_file)

            try:
                response = self.upload_image(
                    image_path,
                    gallery_id=gallery_id,
                    thumbnail_size=thumbnail_size,
                    thumbnail_format=thumbnail_format
                )

                if response.get('status') == 'success':
                    if pbar:
                        pbar.set_postfix_str(f"\u2713 {image_file}")
                    return image_file, response['data'], None
                else:
                    error_msg = f"API error: {response}"
                    if pbar:
                        pbar.set_postfix_str(f"\u2717 {image_file}")
                    return image_file, None, error_msg

            except Exception as e:
                error_msg = f"Network error: {str(e)}"
                if pbar:
                    pbar.set_postfix_str(f"\u2717 {image_file}")
                return image_file, None, error_msg

        # Upload images with retries, maintaining order
        uploaded_images = []
        failed_images = []

        # Rolling concurrency: keep N workers busy until all submitted
        with tqdm(total=len(image_files), initial=initial_completed, desc=f"Uploading to {gallery_name}", unit="img", leave=False) as pbar:
            with ThreadPoolExecutor(max_workers=parallel_batch_size) as executor:
                import queue
                remaining = queue.Queue()
                for f in files_to_upload:
                    remaining.put(f)
                futures_map = {}
                # Prime the pool
                for _ in range(min(parallel_batch_size, remaining.qsize())):
                    img = remaining.get()
                    futures_map[executor.submit(upload_single_image, img, 1, pbar)] = img

                while futures_map:
                    done, _ = concurrent.futures.wait(list(futures_map.keys()), return_when=concurrent.futures.FIRST_COMPLETED)
                    for fut in done:
                        img = futures_map.pop(fut)
                        image_file, image_data, error = fut.result()
                        if image_data:
                            uploaded_images.append((image_file, image_data))
                        else:
                            failed_images.append((image_file, error))
                        pbar.update(1)
                        # Submit next if any left
                        if not remaining.empty():
                            nxt = remaining.get()
                            futures_map[executor.submit(upload_single_image, nxt, 1, pbar)] = nxt

        # Retry failed uploads with progress bar
        retry_count = 0
        while failed_images and retry_count < max_retries:
            retry_count += 1
            retry_failed = []

            with tqdm(total=len(failed_images), desc=f"Retry {retry_count}/{max_retries}", unit="img", leave=False) as retry_pbar:
                with ThreadPoolExecutor(max_workers=parallel_batch_size) as executor:
                    import queue
                    remaining = queue.Queue()
                    for img, _ in failed_images:
                        remaining.put(img)
                    futures_map = {}
                    for _ in range(min(parallel_batch_size, remaining.qsize())):
                        img = remaining.get()
                        futures_map[executor.submit(upload_single_image, img, retry_count + 1, retry_pbar)] = img

                    while futures_map:
                        done, _ = concurrent.futures.wait(list(futures_map.keys()), return_when=concurrent.futures.FIRST_COMPLETED)
                        for fut in done:
                            img = futures_map.pop(fut)
                            image_file, image_data, error = fut.result()
                            if image_data:
                                uploaded_images.append((image_file, image_data))
                            else:
                                retry_failed.append((image_file, error))
                            retry_pbar.update(1)
                            if not remaining.empty():
                                nxt = remaining.get()
                                futures_map[executor.submit(upload_single_image, nxt, retry_count + 1, retry_pbar)] = nxt

            failed_images = retry_failed

        # Sort uploaded images by original file order
        uploaded_images.sort(key=lambda x: image_files.index(x[0]))

        # Add to results in correct order
        for _, image_data in uploaded_images:
            results['images'].append(image_data)

        # Calculate statistics
        end_time = time.time()
        upload_time = end_time - start_time

        # Calculate transfer speed
        uploaded_size = initial_uploaded_size + sum(os.path.getsize(os.path.join(folder_path, img_file))
                           for img_file, _ in uploaded_images)
        transfer_speed = uploaded_size / upload_time if upload_time > 0 else 0

        # Calculate image dimension statistics
        successful_dimensions = []
        if initial_completed == 1:
            try:
                successful_dimensions.append(image_dimensions[image_files.index(image_files[0])])
            except Exception:
                pass
        successful_dimensions.extend([image_dimensions[image_files.index(img_file)]
                               for img_file, _ in uploaded_images])
        avg_width = sum(w for w, h in successful_dimensions) / len(successful_dimensions) if successful_dimensions else 0
        avg_height = sum(h for w, h in successful_dimensions) / len(successful_dimensions) if successful_dimensions else 0
        log(f"Successful dimensions: {successful_dimensions}", level="debug", category="uploads")
        max_width = max(w for w, h in successful_dimensions) if successful_dimensions else 0
        max_height = max(h for w, h in successful_dimensions) if successful_dimensions else 0
        min_width = min(w for w, h in successful_dimensions) if successful_dimensions else 0
        min_height = min(h for w, h in successful_dimensions) if successful_dimensions else 0

        # Add statistics to results
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
            'failed_count': len(failed_images)
        })

        # Ensure .uploaded exists; do not create separate gallery_{id} folder
        uploaded_subdir = os.path.join(folder_path, ".uploaded")
        os.makedirs(uploaded_subdir, exist_ok=True)

        # Build filenames
        _, json_filename, bbcode_filename = build_gallery_filenames(gallery_name, gallery_id)

        # Prepare template data
        all_images_bbcode = ""
        for image_data in results['images']:
            all_images_bbcode += image_data['bbcode'] + "  "

        # Calculate folder size (binary units)
        try:
            folder_size = format_binary_size(total_size, precision=1)
        except Exception:
            folder_size = f"{int(total_size)} B"

        # Get most common extension
        extensions = []
        if initial_completed == 1:
            try:
                extensions.append(os.path.splitext(image_files[0])[1].upper().lstrip('.'))
            except Exception:
                pass
        extensions.extend([os.path.splitext(img_file)[1].upper().lstrip('.')
                     for img_file, _ in uploaded_images])
        extension = max(set(extensions), key=extensions.count) if extensions else "JPG"

        # Prepare template data
        template_data = {
            'folder_name': original_name,
            'width': int(avg_width),
            'height': int(avg_height),
            'longest': int(max(avg_width, avg_height)),
            'extension': extension,
            'picture_count': initial_completed + len(uploaded_images),
            'folder_size': folder_size,
            'gallery_link': f"https://imx.to/g/{gallery_id}",
            'all_images': all_images_bbcode.strip()
        }

        # Generate bbcode using specified template and save artifacts centrally
        bbcode_content = generate_bbcode_from_template(template_name, template_data)
        try:
            save_gallery_artifacts(
                folder_path=folder_path,
                results={
                    'gallery_id': gallery_id,
                    'gallery_name': original_name,
                    'images': results['images'],
                    'total_size': total_size,
                    'successful_count': results.get('successful_count', 0),
                    'failed_count': results.get('failed_count', 0),
                    'upload_time': upload_time,
                    'uploaded_size': uploaded_size,
                    'transfer_speed': transfer_speed,
                    'avg_width': avg_width,
                    'avg_height': avg_height,
                    'max_width': max_width,
                    'max_height': max_height,
                    'min_width': min_width,
                    'min_height': min_height,
                    'failed_details': failed_images,
                    'thumbnail_size': thumbnail_size,
                    'thumbnail_format': thumbnail_format,
                    'parallel_batch_size': parallel_batch_size,
                    'total_images': len(image_files),
                    'started_at': datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S'),
                },
                template_name=template_name,
            )
            log("Saved gallery files to central and/or .uploaded as configured", level="debug", category="fileio")
        except Exception as e:
            log(f"Error writing artifacts: {e}", level="error", category="fileio")

        # Compose and save JSON artifact at both locations
        try:
            # Per-image dimensions are known in image_dimensions; map filenames
            dims_by_name = {}
            for idx, (w, h) in enumerate(image_dimensions):
                if idx < len(image_files):
                    dims_by_name[image_files[idx]] = (w, h)

            # Build images list
            images_payload = []
            # Include preseeded first image in JSON payload if present
            if initial_completed == 1 and preseed_images:
                first_fname = image_files[0]
                w, h = dims_by_name.get(first_fname, (0, 0))
                try:
                    size_bytes = os.path.getsize(os.path.join(folder_path, first_fname))
                except Exception:
                    size_bytes = 0
                data0 = preseed_images[0]
                # Ensure lowercase extension
                try:
                    base0, ext0 = os.path.splitext(first_fname)
                    first_fname_norm = base0 + ext0.lower()
                except Exception:
                    first_fname_norm = first_fname
                # Derive thumb_url from image_url if missing
                t0 = data0.get('thumb_url')
                if not t0 and data0.get('image_url'):
                    try:
                        parts = data0.get('image_url').split('/i/')
                        if len(parts) == 2 and parts[1]:
                            img_id = parts[1].split('/')[0]
                            ext_use = ext0.lower() if ext0 else '.jpg'
                            t0 = f"https://imx.to/u/t/{img_id}{ext_use}"
                    except Exception:
                        pass
                images_payload.append({
                    'filename': first_fname_norm,
                    'uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'image_url': data0.get('image_url'),
                    'thumb_url': t0,
                    'bbcode': data0.get('bbcode'),
                    'width': w,
                    'height': h,
                    'size_bytes': size_bytes
                })

            for fname, data in uploaded_images:
                w, h = dims_by_name.get(fname, (0, 0))
                try:
                    size_bytes = os.path.getsize(os.path.join(folder_path, fname))
                except Exception:
                    size_bytes = 0
                # Lowercase extension for filename
                try:
                    base, ext = os.path.splitext(fname)
                    fname_norm = base + ext.lower()
                except Exception:
                    fname_norm = fname
                # Derive thumb_url from image_url if missing
                t = data.get('thumb_url')
                if not t and data.get('image_url'):
                    try:
                        parts = data.get('image_url').split('/i/')
                        if len(parts) == 2 and parts[1]:
                            img_id = parts[1].split('/')[0]
                            ext_use = ext.lower() if ext else '.jpg'
                            t = f"https://imx.to/u/t/{img_id}{ext_use}"
                    except Exception:
                        pass
                images_payload.append({
                    'filename': fname_norm,
                    'uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'image_url': data.get('image_url'),
                    'thumb_url': t,
                    'bbcode': data.get('bbcode'),
                    'width': w,
                    'height': h,
                    'size_bytes': size_bytes
                })

            failures_payload = [
                {
                    'filename': fname,
                    'failed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'reason': reason
                }
                for fname, reason in failed_images
            ]

            json_payload = {
                'meta': {
                    'gallery_name': gallery_name,
                    'gallery_id': gallery_id,
                    'gallery_url': gallery_url,
                    'status': 'completed',
                    'started_at': datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S'),
                    'finished_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'uploader_version': __version__,
                },
                'settings': {
                    'thumbnail_size': thumbnail_size,
                    'thumbnail_format': thumbnail_format,
                    'template_name': template_name,
                    'parallel_batch_size': parallel_batch_size
                },
                'stats': {
                    'total_images': len(image_files),
                    'successful_count': initial_completed + len(uploaded_images),
                    'failed_count': len(failed_images),
                    'upload_time': upload_time,
                    'total_size': total_size,
                    'uploaded_size': uploaded_size,
                    'avg_width': avg_width,
                    'avg_height': avg_height,
                    'max_width': max_width,
                    'max_height': max_height,
                    'min_width': min_width,
                    'min_height': min_height,
                    'transfer_speed_mb_s': transfer_speed / (1024*1024) if transfer_speed else 0
                },
                'images': images_payload,
                'failures': failures_payload,
                'bbcode_full': bbcode_content
            }

            # Save JSON to .uploaded
            uploaded_json_path = os.path.join(uploaded_subdir, json_filename)
            with open(uploaded_json_path, 'w', encoding='utf-8') as jf:
                json.dump(json_payload, jf, ensure_ascii=False, indent=2)

            # Save JSON to central (use helper paths; central_path defined earlier may not exist here)
            try:
                central_path = get_central_storage_path()
                central_json_path = os.path.join(central_path, json_filename)
                with open(central_json_path, 'w', encoding='utf-8') as jf:
                    json.dump(json_payload, jf, ensure_ascii=False, indent=2)
            except Exception:
                pass
        except Exception as e:
            log(f"Error writing JSON artifact: {e}", level="error", category="fileio")

        return results
