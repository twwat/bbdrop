"""
File host upload client using pycurl for bandwidth tracking and progress callbacks.
"""

import pycurl
import json
import hashlib
import time
import re
import base64
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from io import BytesIO
from urllib.parse import quote

from src.core.file_host_config import HostConfig
from src.core.engine import AtomicCounter
from src.utils.logger import log


class FileHostClient:
    """pycurl-based file host uploader with bandwidth tracking."""

    def __init__(
        self,
        host_config: HostConfig,
        bandwidth_counter: AtomicCounter,
        credentials: Optional[str] = None,
        host_id: Optional[str] = None,
        log_callback: Optional[Callable[[str, str], None]] = None
    ):
        """Initialize file host client.

        Args:
            host_config: Host configuration
            bandwidth_counter: Atomic counter for bandwidth tracking
            credentials: Optional credentials (username:password or api_key)
            host_id: Optional host identifier for token caching
            log_callback: Optional logging callback from worker
        """
        self.config = host_config
        self.bandwidth_counter = bandwidth_counter
        self.credentials = credentials
        self.host_id = host_id
        self._log_callback = log_callback
        # Progress tracking
        self.last_uploaded = 0
        self.should_stop_func: Optional[Callable[[], bool]] = None
        self.on_progress_func: Optional[Callable[[int, int], None]] = None

        # Authentication token (for token-based auth)
        self.auth_token: Optional[str] = None

        # Session cookies (for session-based auth)
        self.cookie_jar: Dict[str, str] = {}

        # Opportunistically cached storage from login (avoids extra API call)
        self._cached_storage_from_login: Optional[Dict[str, Any]] = None

        # Login if credentials provided and auth required
        if self.config.requires_auth and credentials:
            if self.config.auth_type == "token_login":
                # Try to use cached token first
                if host_id:
                    from src.network.token_cache import get_token_cache
                    token_cache = get_token_cache()
                    cached_token = token_cache.get_token(host_id)
                    if cached_token:
                        if self._log_callback: self._log_callback(f"Using cached token for {self.config.name}", "debug")
                        self.auth_token = cached_token
                    else:
                        # Login and cache the token
                        self.auth_token = self._login_token_based(credentials)
                        if self.auth_token:
                            token_cache.store_token(host_id, self.auth_token, self.config.token_ttl)
                else:
                    # No host_id provided, just login without caching
                    self.auth_token = self._login_token_based(credentials)
            elif self.config.auth_type == "session":
                self._login_session_based(credentials)

    def _login_token_based(self, credentials: str) -> str:
        """Login to get authentication token.

        Args:
            credentials: username:password

        Returns:
            Authentication token

        Raises:
            ValueError: If login fails
        """
        if ':' not in credentials:
            raise ValueError(f"{self.config.name} requires credentials in format 'username:password'")

        username, password = credentials.split(':', 1)

        # Build login URL with parameters
        login_data = {}
        for field, template in self.config.login_fields.items():
            value = template.replace("{username}", username).replace("{password}", password)
            login_data[field] = value

        login_url = self.config.login_url
        if login_data:
            params = "&".join(f"{k}={quote(str(v))}" for k, v in login_data.items())
            login_url = f"{login_url}?{params}"

        if self._log_callback: self._log_callback(f"Logging in to {self.config.name}...", "debug")

        # Perform login request
        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, login_url)
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.TIMEOUT, 30)
            curl.setopt(pycurl.FOLLOWLOCATION, True)

            curl.perform()
            response_code = curl.getinfo(pycurl.RESPONSE_CODE)

            if response_code != 200:
                raise ValueError(f"Login failed with status {response_code}")

            response_text = response_buffer.getvalue().decode('utf-8')
            data = json.loads(response_text)

            # Check API status
            api_status = data.get("status")
            if api_status and api_status != 200:
                error_msg = self._extract_from_json(data, ["response", "details"]) or \
                           self._extract_from_json(data, ["response", "msg"]) or \
                           f"API returned status {api_status}"
                raise ValueError(f"Login failed: {error_msg}")

            # Extract token
            if not self.config.token_path:
                raise ValueError("token_path not configured")

            token = self._extract_from_json(data, self.config.token_path)
            if not token:
                raise ValueError("Failed to extract token from login response")

            # Opportunistically extract storage info if present in login response
            # This avoids needing a separate /info API call
            storage_info = {}
            if self.config.storage_total_path:
                storage_total = self._extract_from_json(data, self.config.storage_total_path)
                if storage_total is not None:
                    storage_info['storage_total'] = storage_total

            if self.config.storage_left_path:
                storage_left = self._extract_from_json(data, self.config.storage_left_path)
                if storage_left is not None:
                    storage_info['storage_left'] = storage_left

            if self.config.storage_used_path:
                storage_used = self._extract_from_json(data, self.config.storage_used_path)
                if storage_used is not None:
                    storage_info['storage_used'] = storage_used

            # Store for potential access by caller
            if storage_info:
                self._cached_storage_from_login = storage_info

                storage_formatted = json.dumps(storage_info, indent=2).replace(chr(10), '\\n')
                log(
                    f"Opportunistically cached storage from login: {storage_formatted}",
                    level="debug",
                    category="file_hosts"
                )

            if self._log_callback: self._log_callback(f"Successfully logged in to {self.config.name}", "info")
            return token

        finally:
            curl.close()

    def _login_session_based(self, credentials: str) -> None:
        """Login to establish session cookies.

        Args:
            credentials: username:password

        Raises:
            ValueError: If login fails
        """
        if ':' not in credentials:
            raise ValueError(f"{self.config.name} requires credentials in format 'username:password'")

        username, password = credentials.split(':', 1)

        if self._log_callback: self._log_callback(f"Logging in to {self.config.name} (session-based)...", "debug")

        # Step 1: GET login page first (establishes initial cookies, extracts CSRF tokens)
        get_curl = pycurl.Curl()
        get_buffer = BytesIO()
        get_headers = BytesIO()

        try:
            get_curl.setopt(pycurl.URL, self.config.login_url)
            get_curl.setopt(pycurl.WRITEDATA, get_buffer)
            get_curl.setopt(pycurl.HEADERFUNCTION, get_headers.write)
            get_curl.setopt(pycurl.TIMEOUT, 30)
            get_curl.perform()

            # Extract cookies from GET request
            headers = get_headers.getvalue().decode('utf-8')
            for line in headers.split('\r\n'):
                if line.lower().startswith('set-cookie:'):
                    cookie = line.split(':', 1)[1].strip()
                    cookie_parts = cookie.split(';')[0]
                    if '=' in cookie_parts:
                        name, value = cookie_parts.split('=', 1)
                        self.cookie_jar[name] = value

            # Extract ALL hidden fields from login form
            page_html = get_buffer.getvalue().decode('utf-8', errors='ignore')
            import re
            hidden_fields = {}
            for match in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', page_html):
                input_tag = match.group(0)
                name_match = re.search(r'name=["\']([^"\']+)["\']', input_tag)
                value_match = re.search(r'value=["\']([^"\']*)["\']', input_tag)
                if name_match:
                    field_name = name_match.group(1)
                    field_value = value_match.group(1) if value_match else ''
                    hidden_fields[field_name] = field_value
            
            if self._log_callback: self._log_callback(f"Extracted hidden fields: {list(hidden_fields.keys())}", "debug")
            
            # Extract captcha if configured
            captcha_code = None
            if self.config.captcha_regex:
                captcha_match = re.search(self.config.captcha_regex, page_html, re.DOTALL)
                if captcha_match:
                    captcha_area = captcha_match.group(0)
                    
                    # Extract all span tags with padding-left and digit
                    # Format: <span style="...padding-left:26px...">2</span> or &#50;
                    digit_positions = []
                    for span_match in re.finditer(r'<span[^>]*padding-left:\s*(\d+)px[^>]*>([^<]+)</span>', captcha_area):
                        position = int(span_match.group(1))
                        digit_html = span_match.group(2)
                        
                        # Decode HTML entity if present (&#50; -> '2')
                        entity_match = re.search(r'&#(\d+);', digit_html)
                        if entity_match:
                            digit = chr(int(entity_match.group(1)))
                        else:
                            digit = digit_html.strip()
                        
                        digit_positions.append((position, digit))
                    
                    if digit_positions:
                        # Sort by position (left to right)
                        digit_positions.sort(key=lambda x: x[0])
                        captcha_raw = ''.join(d for _, d in digit_positions)
                        
                        # Apply transformation if specified
                        if self.config.captcha_transform == "move_3rd_to_front":
                            # Move 3rd character to front: "1489" -> "8149"
                            if len(captcha_raw) >= 3:
                                captcha_code = captcha_raw[2] + captcha_raw[:2] + captcha_raw[3:]
                            else:
                                captcha_code = captcha_raw
                        elif self.config.captcha_transform == "reverse":
                            captcha_code = captcha_raw[::-1]
                        else:
                            captcha_code = captcha_raw
                        
                        if self._log_callback: self._log_callback(f"Solved captcha: {captcha_raw} -> {captcha_code} (sorted by CSS position)", "debug")
                    else:
                        if self._log_callback: self._log_callback(f"Warning: Could not extract captcha digits from matched area", "warning")
                else:
                    if self._log_callback: self._log_callback(f"Warning: Could not extract captcha using regex", "warning")

        finally:
            get_curl.close()

        # Step 2: Build login data, starting with hidden fields
        login_data = hidden_fields.copy()  # Start with all hidden fields (token, rand, etc.)
        
        # Override with configured login fields
        for field, template in self.config.login_fields.items():
            value = template.replace("{username}", username).replace("{password}", password)
            login_data[field] = value
        
        # Add captcha if extracted
        if captcha_code:
            login_data[self.config.captcha_field] = captcha_code

        # Step 3: POST login credentials
        post_curl = pycurl.Curl()
        post_buffer = BytesIO()
        post_headers = BytesIO()

        try:
            post_curl.setopt(pycurl.URL, self.config.login_url)
            post_curl.setopt(pycurl.POST, 1)
            post_curl.setopt(pycurl.POSTFIELDS, "&".join(f"{k}={quote(v)}" for k, v in login_data.items()))
            post_curl.setopt(pycurl.WRITEDATA, post_buffer)
            post_curl.setopt(pycurl.HEADERFUNCTION, post_headers.write)
            post_curl.setopt(pycurl.TIMEOUT, 30)
            post_curl.setopt(pycurl.FOLLOWLOCATION, True)

            # Send cookies from GET request
            if self.cookie_jar:
                cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookie_jar.items())
                post_curl.setopt(pycurl.COOKIE, cookie_str)

            post_curl.perform()
            response_code = post_curl.getinfo(pycurl.RESPONSE_CODE)

            if response_code not in [200, 302]:
                raise ValueError(f"Login failed with status {response_code}")

            # Extract cookies from POST response
            headers = post_headers.getvalue().decode('utf-8')
            for line in headers.split('\r\n'):
                if line.lower().startswith('set-cookie:'):
                    cookie = line.split(':', 1)[1].strip()
                    cookie_parts = cookie.split(';')[0]
                    if '=' in cookie_parts:
                        name, value = cookie_parts.split('=', 1)
                        self.cookie_jar[name] = value

            if not self.cookie_jar:
                raise ValueError("Login failed: No session cookies received")

            if self._log_callback: self._log_callback(f"Successfully logged in to {self.config.name}", "info")

        finally:
            post_curl.close()

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file.

        Args:
            file_path: Path to file

        Returns:
            MD5 hash as hex string
        """
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def _extract_from_json(self, data: Any, path: list) -> Any:
        """Extract value from JSON using path (supports dict keys and array indices).

        Args:
            data: JSON data
            path: List of keys/indices to traverse

        Returns:
            Extracted value or None
        """
        result = data
        for key in path:
            if isinstance(result, dict):
                result = result.get(key)
            elif isinstance(result, list) and isinstance(key, int):
                result = result[key] if key < len(result) else None
            else:
                return None
            if result is None:
                return None
        return result

    def _xferinfo_callback(self, download_total, downloaded, upload_total, uploaded):
        """pycurl progress callback.

        Args:
            download_total: Total bytes to download
            downloaded: Bytes downloaded so far
            upload_total: Total bytes to upload
            uploaded: Bytes uploaded so far

        Returns:
            0 to continue, 1 to abort
        """
        # Update bandwidth counter
        bytes_since_last = uploaded - self.last_uploaded
        if bytes_since_last > 0:
            self.bandwidth_counter.add(bytes_since_last)
            self.last_uploaded = uploaded

        # Check for cancellation
        if self.should_stop_func and self.should_stop_func():
            return 1  # Abort transfer

        # Notify progress
        if self.on_progress_func and upload_total > 0:
            self.on_progress_func(uploaded, upload_total)

        return 0

    def upload_file(
        self,
        file_path: Path,
        on_progress: Optional[Callable[[int, int], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """Upload file to file host.

        Args:
            file_path: Path to file to upload
            on_progress: Optional progress callback (uploaded_bytes, total_bytes)
            should_stop: Optional cancellation check callback

        Returns:
            Dictionary with upload results

        Raises:
            Exception: If upload fails
        """
        self.on_progress_func = on_progress
        self.should_stop_func = should_stop
        self.last_uploaded = 0

        if self._log_callback: self._log_callback(f"Uploading {file_path.name} to {self.config.name}...", "info")

        # Handle multi-step uploads (like RapidGator)
        if self.config.upload_init_url:
            try:
                return self._upload_multistep(file_path)
            except Exception as e:
                # If we get a 401 error and we're using token auth, try refreshing the token
                if "401" in str(e) and self.config.auth_type == "token_login" and self.host_id and self.credentials:
                    if self._log_callback: self._log_callback(f"Got 401 error, refreshing token and retrying...", "warning")

                    # Clear cached token
                    from src.network.token_cache import get_token_cache
                    token_cache = get_token_cache()
                    token_cache.clear_token(self.host_id)

                    # Login fresh
                    self.auth_token = self._login_token_based(self.credentials)
                    if self.auth_token:
                        token_cache.store_token(self.host_id, self.auth_token, self.config.token_ttl)

                    # Retry upload
                    return self._upload_multistep(file_path)
                else:
                    raise

        # Standard upload
        return self._upload_standard(file_path)

    def _upload_standard(self, file_path: Path) -> Dict[str, Any]:
        """Perform standard single-step upload.

        Args:
            file_path: Path to file

        Returns:
            Upload result dictionary
        """
        # Get upload URL
        upload_url = self.config.upload_endpoint

        # Replace filename placeholder
        if "{filename}" in upload_url:
            upload_url = upload_url.replace("{filename}", file_path.name)

        # Get server if needed
        if self.config.get_server:
            upload_url = self._get_upload_server()

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, upload_url)
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.TIMEOUT, 300)
            curl.setopt(pycurl.FOLLOWLOCATION, True)

            # Set up progress callbacks
            curl.setopt(pycurl.NOPROGRESS, False)
            curl.setopt(pycurl.XFERINFOFUNCTION, self._xferinfo_callback)

            # Prepare headers
            headers = self._prepare_headers()
            if headers:
                curl.setopt(pycurl.HTTPHEADER, [f"{k}: {v}" for k, v in headers.items()])

            # Session cookies
            if self.cookie_jar:
                cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookie_jar.items())
                curl.setopt(pycurl.COOKIE, cookie_str)

            # Extract session ID for session-based uploads (before upload)
            sess_id = None
            if self.config.auth_type == "session":
                # Method 1: Use cookie value directly (e.g., FileSpace uses xfss cookie)
                if self.config.session_cookie_name:
                    if self.config.session_cookie_name in self.cookie_jar:
                        sess_id = self.cookie_jar[self.config.session_cookie_name]
                        if self._log_callback: self._log_callback(f"Using {self.config.session_cookie_name} cookie as sess_id: {sess_id[:20]}...", "debug")
                    else:
                        if self._log_callback: self._log_callback(f"Warning: {self.config.session_cookie_name} cookie not found in cookie jar", "warning")
                
                # Method 2: Extract from upload page HTML using regex (e.g., FileDot)
                elif self.config.session_id_regex:
                    # Visit upload page to extract fresh session ID
                    upload_page_url = self.config.upload_page_url
                    if not upload_page_url:
                        # Fallback: derive from upload_endpoint (remove /upload.cgi or similar)
                        import re
                        base_url = re.sub(r'/[^/]*$', '', upload_url)
                        upload_page_url = f"{base_url}/upload"
                    
                    if self._log_callback: self._log_callback(f"Visiting upload page to extract session ID: {upload_page_url}", "debug")
                    
                    page_curl = pycurl.Curl()
                    page_buffer = BytesIO()
                    try:
                        page_curl.setopt(pycurl.URL, upload_page_url)
                        page_curl.setopt(pycurl.WRITEDATA, page_buffer)
                        page_curl.setopt(pycurl.TIMEOUT, 30)
                        
                        # Use session cookies
                        if self.cookie_jar:
                            page_curl.setopt(pycurl.COOKIE, cookie_str)
                        
                        page_curl.perform()
                        page_html = page_buffer.getvalue().decode('utf-8')
                        
                        # Extract session ID using regex
                        import re
                        match = re.search(self.config.session_id_regex, page_html)
                        if match:
                            sess_id = match.group(1)
                            if self._log_callback: self._log_callback(f"Extracted session ID: {sess_id[:20]}...", "debug")
                        else:
                            if self._log_callback: self._log_callback(f"Warning: Could not extract session ID from upload page", "warning")
                    finally:
                        page_curl.close()

            # Upload file
            file_size = file_path.stat().st_size

            if self.config.method == "PUT":
                with open(file_path, 'rb') as f:
                    curl.setopt(pycurl.UPLOAD, 1)
                    curl.setopt(pycurl.READDATA, f)
                    curl.setopt(pycurl.INFILESIZE, file_size)
                    curl.perform()
            else:
                # POST with multipart form data
                form_fields = [
                    (self.config.file_field, (
                        pycurl.FORM_FILE, str(file_path),
                        pycurl.FORM_FILENAME, file_path.name
                    )),
                    *[(k, v) for k, v in self.config.extra_fields.items()]
                ]
                
                # Add session ID if extracted
                if sess_id:
                    form_fields.append(('sess_id', sess_id))
                
                curl.setopt(pycurl.HTTPPOST, form_fields)
                curl.perform()

            response_code = curl.getinfo(pycurl.RESPONSE_CODE)

            if response_code not in [200, 201]:
                raise Exception(f"Upload failed with status {response_code}")

            response_text = response_buffer.getvalue().decode('utf-8')
            return self._parse_response(response_text, response_code)

        finally:
            curl.close()

    def _upload_multistep(self, file_path: Path) -> Dict[str, Any]:
        """Perform multi-step upload (init → upload → poll).

        Args:
            file_path: Path to file

        Returns:
            Upload result dictionary
        """
        file_size = file_path.stat().st_size

        # Step 1: Calculate hash if required
        file_hash = None
        if self.config.require_file_hash:
            log("Calculating file hash...", "debug")
            file_hash = self._calculate_file_hash(file_path)

        # Step 2: Initialize upload
        init_url = self.config.upload_init_url
        replacements = {
            "filename": file_path.name,
            "size": str(file_size),
            "token": self.auth_token or "",
            "hash": file_hash or ""
        }

        for key, value in replacements.items():
            init_url = init_url.replace(f"{{{key}}}", value)

        log("Initializing upload...", "debug")

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, init_url)
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.TIMEOUT, 30)
            curl.perform()

            response_code = curl.getinfo(pycurl.RESPONSE_CODE)

            # Always try to parse response body for detailed error messages
            response_text = response_buffer.getvalue().decode('utf-8')
            try:
                init_data = json.loads(response_text)
            except:
                init_data = {}

            if response_code != 200:
                # Try to extract detailed error from API response
                api_status = init_data.get("status")
                error_details = self._extract_from_json(init_data, ["response", "details"]) or \
                               self._extract_from_json(init_data, ["response", "msg"]) or \
                               self._extract_from_json(init_data, ["error"]) or \
                               response_text[:200]  # First 200 chars of response

                raise Exception(f"Upload init failed (HTTP {response_code}, API status {api_status}): {error_details}")

            # Check API status even if HTTP was 200
            api_status = init_data.get("status")
            if api_status and api_status != 200:
                error_msg = self._extract_from_json(init_data, ["response", "details"]) or \
                           self._extract_from_json(init_data, ["response", "msg"]) or \
                           f"API returned status {api_status}"
                raise Exception(f"Upload initialization failed: {error_msg}")

            # Extract upload URL and ID
            upload_url = self._extract_from_json(init_data, self.config.upload_url_path)
            upload_id = self._extract_from_json(init_data, self.config.upload_id_path)
            upload_state = self._extract_from_json(init_data, ["response", "upload", "state"])

            # Check for deduplication (file already exists)
            if upload_state == 2 or (upload_url is None and upload_state is not None):
                existing_url = self._extract_from_json(init_data, ["response", "upload", "file", "url"])
                if existing_url:
                    log("File already exists on server (deduplication)", "info")
                    return {
                        "status": "success",
                        "url": existing_url,
                        "upload_id": upload_id,
                        "deduplication": True,
                        "raw_response": init_data
                    }

            if not upload_url:
                raise Exception("Failed to get upload URL from initialization response")

            if not upload_id:
                raise Exception("Failed to get upload ID from initialization response")

            if self._log_callback: self._log_callback(f"Got upload ID: {upload_id}", "debug")

        finally:
            curl.close()

        # Step 3: Upload file
        log("Uploading file...", "debug")

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            with open(file_path, 'rb') as f:
                curl.setopt(pycurl.URL, upload_url)
                curl.setopt(pycurl.WRITEDATA, response_buffer)
                curl.setopt(pycurl.TIMEOUT, 300)
                curl.setopt(pycurl.NOPROGRESS, False)
                curl.setopt(pycurl.XFERINFOFUNCTION, self._xferinfo_callback)

                curl.setopt(pycurl.HTTPPOST, [
                    (self.config.file_field, (
                        pycurl.FORM_FILE, str(file_path),
                        pycurl.FORM_FILENAME, file_path.name
                    ))
                ])

                curl.perform()

                response_code = curl.getinfo(pycurl.RESPONSE_CODE)
                if response_code not in [200, 201]:
                    raise Exception(f"File upload failed with status {response_code}")

        finally:
            curl.close()

        # Step 4: Poll for completion
        if self.config.upload_poll_url:
            log("Waiting for upload processing...", "debug")
            time.sleep(self.config.upload_poll_delay)

            poll_url = self.config.upload_poll_url.replace("{upload_id}", upload_id).replace("{token}", self.auth_token or "")

            for attempt in range(self.config.upload_poll_retries):
                curl = pycurl.Curl()
                response_buffer = BytesIO()

                try:
                    curl.setopt(pycurl.URL, poll_url)
                    curl.setopt(pycurl.WRITEDATA, response_buffer)
                    curl.setopt(pycurl.TIMEOUT, 30)
                    curl.perform()

                    poll_data = json.loads(response_buffer.getvalue().decode('utf-8'))

                    if self._log_callback: self._log_callback(f"Poll attempt {attempt + 1}/{self.config.upload_poll_retries}, response: {json.dumps(poll_data)[:200]}", "debug")

                    # Check for final URL
                    final_url = self._extract_from_json(poll_data, self.config.link_path)
                    if final_url:
                        log("Upload complete!", "info")
                        return {
                            "status": "success",
                            "url": final_url,
                            "upload_id": upload_id,
                            "file_id": upload_id,
                            "raw_response": poll_data
                        }

                    # Check for upload state to see if it's still processing
                    state = self._extract_from_json(poll_data, ["response", "upload", "state"])
                    if state == 2:
                        # State 2 means upload is complete - try alternate URL path
                        alternate_url = self._extract_from_json(poll_data, ["response", "file", "url"])
                        if not alternate_url:
                            # Try another path
                            alternate_url = self._extract_from_json(poll_data, ["response", "upload", "file_url"])

                        if alternate_url:
                            if self._log_callback: self._log_callback(f"Upload complete (state 2, alternate path)!", "info")
                            return {
                                "status": "success",
                                "url": alternate_url,
                                "upload_id": upload_id,
                                "file_id": upload_id,
                                "raw_response": poll_data
                            }

                    # Not ready yet, wait and retry
                    if attempt < self.config.upload_poll_retries - 1:
                        time.sleep(self.config.upload_poll_delay)

                finally:
                    curl.close()

            # If we got here, polling timed out - log the last response
            if self._log_callback: self._log_callback(f"Upload polling timeout. Last response: {json.dumps(poll_data) if 'poll_data' in locals() else 'No response'}", "warning")
            raise Exception(f"Upload processing timeout - file may still be uploading (got upload_id: {upload_id})")

        # No polling configured
        return {
            "status": "success",
            "url": "",
            "upload_id": upload_id,
            "raw_response": init_data
        }

    def _get_upload_server(self) -> str:
        """Get upload server URL.

        Returns:
            Upload server URL
        """
        if not self.config.get_server:
            return self.config.upload_endpoint

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, self.config.get_server)
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.TIMEOUT, 10)
            curl.perform()

            data = json.loads(response_buffer.getvalue().decode('utf-8'))

            # Extract server URL using configured path
            if self.config.server_response_path:
                server_url = self._extract_from_json(data, self.config.server_response_path)
                if server_url:
                    return self.config.upload_endpoint.replace("{server}", server_url)

            # Fallback: GoFile compatibility (legacy)
            if "gofile" in self.config.name.lower() and "data" in data and "server" in data["data"]:
                server = data["data"]["server"]
                return self.config.upload_endpoint.replace("{server}", server)

            return self.config.upload_endpoint

        finally:
            curl.close()

    def _prepare_headers(self) -> Dict[str, str]:
        """Prepare HTTP headers.

        Returns:
            Dictionary of headers
        """
        headers = {}

        if self.auth_token and self.config.auth_type:
            if self.config.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {self.auth_token}"
            elif self.config.auth_type == "basic":
                auth_string = base64.b64encode(f":{self.auth_token}".encode()).decode()
                headers["Authorization"] = f"Basic {auth_string}"

        return headers

    def _parse_response(self, response_text: str, response_code: int) -> Dict[str, Any]:
        """Parse upload response and extract download link.

        Args:
            response_text: Response body
            response_code: HTTP status code

        Returns:
            Result dictionary with status and URL
        """
        result = {
            "status": "success",
            "timestamp": time.time()
        }

        if self.config.response_type == "json":
            data = json.loads(response_text)
            result["raw_response"] = data

            # Handle array responses
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            # Extract link using JSON path
            if self.config.link_path:
                link = self._extract_from_json(data, self.config.link_path)
                if link:
                    result["url"] = self.config.link_prefix + str(link) + self.config.link_suffix

                    # Apply regex transformation
                    if self.config.link_regex:
                        match = re.search(self.config.link_regex, result["url"])
                        if match and match.groups():
                            result["url"] = self.config.link_prefix + match.group(1) + self.config.link_suffix

        elif self.config.response_type == "text":
            result["raw_response"] = response_text

            if self.config.link_regex:
                match = re.search(self.config.link_regex, response_text)
                if match:
                    extracted = match.group(1) if match.groups() else match.group(0)
                    result["url"] = self.config.link_prefix + extracted + self.config.link_suffix
            else:
                result["url"] = response_text.strip()

        elif self.config.response_type == "redirect":
            # URL should be in Location header (handled by pycurl FOLLOWLOCATION)
            result["url"] = ""

        return result

    def delete_file(self, file_id: str) -> Dict[str, Any]:
        """Delete a file from the host.

        Args:
            file_id: File ID to delete

        Returns:
            Result dictionary

        Raises:
            Exception: If delete fails or not supported
        """
        if not self.config.delete_url:
            raise Exception(f"{self.config.name} does not support file deletion")

        # Build delete URL with parameters
        delete_url = self.config.delete_url
        replacements = {
            "file_id": file_id,
            "token": self.auth_token or ""
        }

        for key, value in replacements.items():
            delete_url = delete_url.replace(f"{{{key}}}", value)

        if self._log_callback: self._log_callback(f"Deleting file {file_id} from {self.config.name}...", "debug")

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, delete_url)
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.TIMEOUT, 30)

            if self.config.delete_method == "DELETE":
                curl.setopt(pycurl.CUSTOMREQUEST, "DELETE")

            curl.perform()
            response_code = curl.getinfo(pycurl.RESPONSE_CODE)

            if response_code not in [200, 204]:
                raise Exception(f"Delete failed with status {response_code}")

            response_text = response_buffer.getvalue().decode('utf-8')

            if self._log_callback: self._log_callback(f"Successfully deleted file {file_id} from {self.config.name}", "info")

            return {
                "status": "success",
                "file_id": file_id,
                "raw_response": response_text
            }

        finally:
            curl.close()

    def get_user_info(self) -> Dict[str, Any]:
        """Get user info including storage and premium status.

        Returns:
            Dictionary with user info

        Raises:
            Exception: If user info retrieval fails or not supported
        """
        if not self.config.user_info_url:
            raise Exception(f"{self.config.name} does not support user info retrieval")

        # Check authentication based on auth type
        if self.config.auth_type == "token_login":
            if not self.auth_token:
                raise Exception("Authentication token required for user info")
            # Build user info URL with token
            info_url = self.config.user_info_url.replace("{token}", self.auth_token)
        elif self.config.auth_type == "session":
            if not self.cookie_jar:
                raise Exception("Session cookies required for user info")
            # Use URL as-is (no token placeholder)
            info_url = self.config.user_info_url
        else:
            raise Exception(f"Unsupported auth type for user info: {self.config.auth_type}")

        if self._log_callback: self._log_callback(f"Retrieving user info from {self.config.name}...", "debug")

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, info_url)
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.TIMEOUT, 30)

            # Send session cookies for session-based auth
            if self.config.auth_type == "session" and self.cookie_jar:
                cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookie_jar.items())
                curl.setopt(pycurl.COOKIE, cookie_str)

            curl.perform()

            response_code = curl.getinfo(pycurl.RESPONSE_CODE)

            if response_code != 200:
                # If we get a 401 error and we're using token auth, try refreshing the token
                if response_code == 401 and self.config.auth_type == "token_login" and self.host_id and self.credentials:
                    curl.close()
                    if self._log_callback: self._log_callback(f"Got 401 error, refreshing token and retrying...", "warning")

                    # Clear cached token
                    from src.network.token_cache import get_token_cache
                    token_cache = get_token_cache()
                    token_cache.clear_token(self.host_id)

                    # Login fresh
                    self.auth_token = self._login_token_based(self.credentials)
                    if self.auth_token:
                        token_cache.store_token(self.host_id, self.auth_token, self.config.token_ttl)

                    # Retry with new token
                    info_url = self.config.user_info_url.replace("{token}", self.auth_token)
                    curl = pycurl.Curl()
                    response_buffer = BytesIO()

                    curl.setopt(pycurl.URL, info_url)
                    curl.setopt(pycurl.WRITEDATA, response_buffer)
                    curl.setopt(pycurl.TIMEOUT, 30)
                    curl.perform()

                    response_code = curl.getinfo(pycurl.RESPONSE_CODE)

                    if response_code != 200:
                        raise Exception(f"User info retrieval failed with status {response_code} (after token refresh)")
                else:
                    raise Exception(f"User info retrieval failed with status {response_code}")

            response_text = response_buffer.getvalue().decode('utf-8')

            # Check if we need HTML parsing (storage_regex) or JSON parsing
            if self.config.storage_regex:
                # HTML response - extract storage using regex
                result = {"raw_response": "HTML response (not logged)"}

                if self._log_callback: self._log_callback(f"Parsing HTML for storage (response length: {len(response_text)} bytes)", "debug")

                match = re.search(self.config.storage_regex, response_text, re.DOTALL)
                if match:
                    # Regex should capture: (used, total) in GB
                    # Example: "566.87 of 10240 GB" -> groups (566.87, 10240)
                    used_gb = float(match.group(1))
                    total_gb = float(match.group(2))

                    # Convert to bytes
                    total_bytes = int(total_gb * 1024 * 1024 * 1024)
                    used_bytes = int(used_gb * 1024 * 1024 * 1024)
                    left_bytes = total_bytes - used_bytes

                    result['storage_total'] = total_bytes
                    result['storage_used'] = used_bytes
                    result['storage_left'] = left_bytes

                    if self._log_callback: self._log_callback(
                        f"Extracted storage from HTML: {used_gb} of {total_gb} GB (left: {(left_bytes / 1024 / 1024 / 1024):.2f} GB)",
                        "debug"
                    )
                else:
                    # Regex didn't match - log entire HTML response for debugging
                    # Escape newlines for log viewer auto-expand (replace \n with literal \\n)
                    response_escaped = response_text.replace('\n', '\\n').replace('\r', '')
                    if self._log_callback: self._log_callback(
                        f"Storage regex did not match HTML response (full response): {response_escaped}",
                        "warning"
                    )
            else:
                # JSON response - extract using JSON paths
                data = json.loads(response_text)
                result = {"raw_response": data}

                if self.config.storage_total_path:
                    result['storage_total'] = self._extract_from_json(data, self.config.storage_total_path)
                    log(
                        f"DEBUG: Extracted storage_total={result.get('storage_total')} using path {self.config.storage_total_path}",
                        level="debug",
                        category="file_hosts"
                    )

                if self.config.storage_left_path:
                    result['storage_left'] = self._extract_from_json(data, self.config.storage_left_path)
                    log(
                        f"DEBUG: Extracted storage_left={result.get('storage_left')} using path {self.config.storage_left_path}",
                        level="debug",
                        category="file_hosts"
                    )

                if self.config.storage_used_path:
                    result['storage_used'] = self._extract_from_json(data, self.config.storage_used_path)

                if self.config.premium_status_path:
                    result['is_premium'] = self._extract_from_json(data, self.config.premium_status_path)

            if self._log_callback: self._log_callback(f"Successfully retrieved user info from {self.config.name}", "info")

            return result

        finally:
            curl.close()

    def test_credentials(self) -> Dict[str, Any]:
        """Test if credentials are valid.

        Returns:
            Dictionary with test results: {success: bool, message: str, user_info: dict}
        """
        try:
            if self.config.requires_auth:
                # Check authentication based on auth type
                if self.config.auth_type == "token_login":
                    if not self.auth_token:
                        return {
                            "success": False,
                            "message": "No authentication token available",
                            "error": "Not logged in"
                        }
                elif self.config.auth_type == "session":
                    if not self.cookie_jar:
                        return {
                            "success": False,
                            "message": "No session cookies available",
                            "error": "Not logged in"
                        }

                # Test using user info endpoint if available
                if self.config.user_info_url:
                    user_info = self.get_user_info()
                    return {
                        "success": True,
                        "message": "Credentials validated successfully",
                        "user_info": user_info
                    }
                else:
                    # No way to test, assume valid if we have a token
                    return {
                        "success": True,
                        "message": "Token exists (unable to verify)",
                        "warning": "No validation endpoint available"
                    }
            else:
                # No auth required
                return {
                    "success": True,
                    "message": "No authentication required"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Credential validation failed: {str(e)}",
                "error": str(e)
            }

    def test_upload(self, cleanup: bool = True) -> Dict[str, Any]:
        """Test upload by uploading a small dummy file.

        Args:
            cleanup: If True, delete the test file after upload

        Returns:
            Dictionary with test results: {success: bool, message: str, file_id: str, url: str}
        """
        import tempfile

        try:
            # Create a small test ZIP file
            test_zip_path = Path(tempfile.gettempdir()) / "test_imxup.zip"

            with zipfile.ZipFile(test_zip_path, 'w', zipfile.ZIP_STORED) as zf:
                # Add a tiny text file to the ZIP
                zf.writestr("test.txt", "imxup test file - safe to delete")

            if self._log_callback: self._log_callback(f"Created test file: {test_zip_path} ({test_zip_path.stat().st_size} bytes)", "debug")

            # Attempt upload
            result = self.upload_file(test_zip_path)

            if result.get('status') == 'success':
                file_id = result.get('upload_id') or result.get('file_id')
                download_url = result.get('url', '')

                # Cleanup: delete the test file if requested and delete is supported
                if cleanup and self.config.delete_url and file_id:
                    try:
                        self.delete_file(file_id)
                        cleanup_msg = " (test file deleted)"
                    except Exception as e:
                        cleanup_msg = f" (cleanup failed: {e})"
                else:
                    cleanup_msg = " (test file not deleted)"

                # Delete local test ZIP
                test_zip_path.unlink(missing_ok=True)

                return {
                    "success": True,
                    "message": f"Upload test successful{cleanup_msg}",
                    "file_id": file_id,
                    "url": download_url
                }
            else:
                # Delete local test ZIP
                test_zip_path.unlink(missing_ok=True)

                return {
                    "success": False,
                    "message": "Upload test failed",
                    "error": result.get('error', 'Unknown error')
                }

        except Exception as e:
            # Clean up test file on error
            if 'test_zip_path' in locals():
                Path(test_zip_path).unlink(missing_ok=True)

            return {
                "success": False,
                "message": f"Upload test failed: {str(e)}",
                "error": str(e)
            }

    def get_cached_storage_from_login(self) -> Optional[Dict[str, Any]]:
        """Get storage data that was opportunistically cached during login.

        This allows callers to get storage info without making a separate /info API call,
        since many APIs return storage data as part of the login response.

        Returns:
            Dictionary with storage_total, storage_left, storage_used if available,
            or None if no storage data was cached during login
        """
        return self._cached_storage_from_login
