"""
IMX.to image host uploader.

Extracted from bbdrop.py — contains the IMX.to API client (ImxToUploader).
"""

import io
import os
import re
import json
import sys
import time
import threading
import mimetypes
from typing import Optional, Any

import requests
from requests.adapters import HTTPAdapter
import pycurl
import certifi

from src.utils.logger import log
from src.utils.credentials import get_credential, decrypt_password
from src.network.image_host_client import ImageHostClient
from src.core.image_host_config import (
    get_image_host_config_manager,
    get_image_host_setting,
    ImageHostConfig,
)
from src.proxy.pycurl_adapter import PyCurlProxyAdapter


class ImxToUploader(ImageHostClient):
    # Browser UA for web-session requests (gallery creation, rename, login)
    _BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0"

    # Type hints for attributes set externally by GUI worker threads
    worker_thread: Optional[Any] = None  # Set by UploadWorker when used in GUI mode

    def _get_credentials(self):
        """Get credentials from stored config (username/password or API key)"""
        # Read from QSettings (Registry) - migration happens at app startup
        encrypted_username = get_credential('username')
        encrypted_password = get_credential('password')
        encrypted_api_key = get_credential('api_key')

        # Decrypt if they exist
        username = decrypt_password(encrypted_username) if encrypted_username else None
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
                'User-Agent': self._BROWSER_USER_AGENT,
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
        self._has_credentials = has_credentials

        if not has_credentials:
            # In CLI mode, exit — no way to set credentials interactively
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
        self._upload_count_lock = threading.Lock()
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
            'User-Agent': self._BROWSER_USER_AGENT,
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
            with self._upload_count_lock:
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
