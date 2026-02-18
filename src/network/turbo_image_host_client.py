"""
TurboImageHost client for image uploads.

Implements ImageHostClient for turboimagehost.com with:
- Variable thumbnail sizes (150-600px)
- Content type selection (family/adult)
- Gallery support with name input
- Optional authentication

Upload flow (verified against real server):
1. POST file to s8d8.turboimagehost.com/upload_html5.tu → JSON {"success":true,"newUrl":"..."}
2. GET newUrl → HTML result page with BBCode, gallery URL, thumbnails

Gallery batching: all images in a gallery share ONE upload_id.
- 1 image on result page → BBCode in <input id="imgCodeIPF">
- N images on result page → BBCode in <textarea id="imgCodeURF">
- Gallery URL in <input id="imgCodeGG"> (when gallery created)
"""

import os
import re
import json
import time
import random
import string
import mimetypes
import threading
from io import BytesIO
from typing import Dict, Any, Optional, Callable, List

import pycurl
import certifi

from src.core.image_host_config import (
    ImageHostConfig,
    get_image_host_config_manager,
    get_image_host_setting,
)
from src.network.image_host_client import ImageHostClient
from src.utils.logger import log


class TurboImageHostClient(ImageHostClient):
    """Client for TurboImageHost uploads via pycurl."""

    # Type hints for attributes
    worker_thread: Optional[Any] = None

    def __init__(self):
        # Initialize image host config (ABC parent)
        _cfg = get_image_host_config_manager().get_host('turbo')
        if _cfg is None:
            _cfg = ImageHostConfig(name="TurboImageHost", host_id="turbo")
        super().__init__(_cfg)

        # TurboImageHost endpoints
        self.base_url = "https://www.turboimagehost.com"
        self._web_url = self.base_url
        self.upload_url = "https://s8d8.turboimagehost.com/upload_html5.tu"
        self.login_url = f"{self.base_url}/login.tu"

        # Load timeout settings via image host config system
        self.upload_connect_timeout = get_image_host_setting('turbo', 'upload_connect_timeout', 'int')
        self.upload_read_timeout = get_image_host_setting('turbo', 'upload_read_timeout', 'int')

        # Connection tracking (thread-safe)
        self._upload_count = 0
        self._upload_count_lock = threading.Lock()

        # Batch upload_id — shared across all images in a gallery.
        # Set on create_gallery=True, used by all subsequent uploads,
        # cleared on clear_api_cookies() (new gallery).
        self._batch_upload_id: Optional[str] = None

        # Cookie jar (dict) — shared across pycurl handles
        self.cookie_jar: Dict[str, str] = {}

        # Thread-local pycurl handles for connection reuse
        self._thread_local = threading.local()
        self._session_lock = threading.Lock()

        # Optional credentials (TurboImageHost works without login)
        self.username = None
        self.password = None
        self._logged_in = False

    def _get_thread_curl(self) -> pycurl.Curl:
        """Get or create a pycurl handle for the current thread. Reuses TCP connection."""
        curl = getattr(self._thread_local, 'curl', None)
        if curl is None:
            curl = pycurl.Curl()
            curl.setopt(pycurl.NOSIGNAL, 1)  # Required for thread safety with timeouts
            self._thread_local.curl = curl
        # reset() clears all options but KEEPS the TCP+TLS connection alive
        curl.reset()
        curl.setopt(pycurl.NOSIGNAL, 1)
        curl.setopt(pycurl.CAINFO, certifi.where())
        curl.setopt(pycurl.SSL_VERIFYPEER, 1)
        curl.setopt(pycurl.SSL_VERIFYHOST, 2)
        curl.setopt(pycurl.USERAGENT,
                     'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0')
        if self.upload_connect_timeout:
            curl.setopt(pycurl.CONNECTTIMEOUT, self.upload_connect_timeout)
        return curl

    def _configure_curl(self, curl: pycurl.Curl) -> None:
        """Apply common SSL/UA/timeout settings to a fresh curl handle."""
        curl.setopt(pycurl.CAINFO, certifi.where())
        curl.setopt(pycurl.SSL_VERIFYPEER, 1)
        curl.setopt(pycurl.SSL_VERIFYHOST, 2)
        curl.setopt(pycurl.FOLLOWLOCATION, True)
        curl.setopt(pycurl.USERAGENT,
                     'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0')
        if self.upload_connect_timeout:
            curl.setopt(pycurl.CONNECTTIMEOUT, self.upload_connect_timeout)

    def _set_cookies(self, curl: pycurl.Curl) -> None:
        """Apply cookie jar to a curl handle."""
        if self.cookie_jar:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookie_jar.items())
            curl.setopt(pycurl.COOKIE, cookie_str)

    def _extract_cookies(self, curl: pycurl.Curl) -> None:
        """Extract Set-Cookie headers from curl into cookie jar."""
        try:
            cookie_list = curl.getinfo(pycurl.INFO_COOKIELIST)
            for cookie_line in cookie_list:
                parts = cookie_line.split('\t')
                if len(parts) >= 7:
                    self.cookie_jar[parts[5]] = parts[6]
        except Exception:
            pass

    def _ensure_session(self) -> None:
        """Fetch session cookie from server if we don't have one yet."""
        if self.cookie_jar:
            return
        with self._session_lock:
            if self.cookie_jar:
                return  # Another thread got it
            curl = pycurl.Curl()
            buf = BytesIO()
            try:
                self._configure_curl(curl)
                curl.setopt(pycurl.COOKIEFILE, "")
                curl.setopt(pycurl.URL, self.base_url)
                curl.setopt(pycurl.WRITEDATA, buf)
                curl.setopt(pycurl.TIMEOUT, 15)
                curl.setopt(pycurl.NOBODY, True)  # HEAD only, skip body
                curl.perform()
                self._extract_cookies(curl)
                if self.cookie_jar:
                    log(f"TurboImageHost session acquired: {list(self.cookie_jar.keys())}",
                        level="debug", category="network")
            except pycurl.error as e:
                log(f"Failed to acquire session cookie: {e}", level="warning", category="network")
            finally:
                curl.close()

    @property
    def web_url(self) -> str:
        """Base web URL for this host."""
        return self._web_url

    @property
    def host_id(self) -> str:
        """Host identifier."""
        return "turbo"

    def login(self, username: str, password: str) -> bool:
        """Login to TurboImageHost (optional - uploads work without login)."""
        curl = pycurl.Curl()
        self._configure_curl(curl)
        # Enable cookie engine so we can extract cookies
        curl.setopt(pycurl.COOKIEFILE, "")

        try:
            # Step 1: GET login page (pick up any cookies)
            buf = BytesIO()
            curl.setopt(pycurl.URL, self.login_url)
            curl.setopt(pycurl.WRITEDATA, buf)
            curl.setopt(pycurl.TIMEOUT, 30)
            curl.perform()
            self._extract_cookies(curl)

            # Step 2: POST login form
            buf = BytesIO()
            curl.setopt(pycurl.URL, f"{self.login_url}?")
            curl.setopt(pycurl.WRITEDATA, buf)
            curl.setopt(pycurl.POST, 1)

            from urllib.parse import quote
            login_fields = f"username={quote(username)}&password={quote(password)}&login=Login"
            curl.setopt(pycurl.POSTFIELDS, login_fields)
            curl.setopt(pycurl.HTTPHEADER, [
                f'Referer: {self.login_url}',
                'Content-Type: application/x-www-form-urlencoded',
            ])
            curl.perform()
            self._extract_cookies(curl)

            response_text = buf.getvalue().decode('utf-8', errors='replace')
            if 'logout' in response_text.lower() or username.lower() in response_text.lower():
                self.username = username
                self.password = password
                self._logged_in = True
                log(f"TurboImageHost login successful for {username}", level="info", category="auth")
                return True
            else:
                log("TurboImageHost login failed - check credentials", level="warning", category="auth")
                return False

        except pycurl.error as e:
            log(f"TurboImageHost login error: {e}", level="error", category="auth")
            return False
        finally:
            curl.close()

    def upload_image(
        self,
        image_path: str,
        create_gallery: bool = False,
        gallery_id: Optional[str] = None,
        thumbnail_size: int = 300,
        thumbnail_format: int = 2,
        thread_session: Optional[Any] = None,
        progress_callback: Optional[Callable] = None,
        gallery_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a single image to TurboImageHost via pycurl."""
        self._ensure_session()
        content_type = get_image_host_setting('turbo', 'content_type', 'str') or 'all'

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        thumbnail_size = max(150, min(600, thumbnail_size))

        filename = os.path.basename(image_path)

        # Pre-read file into memory BEFORE POST to enable true concurrent uploads.
        # FORM_FILE reads from disk during perform(), which gets serialized across
        # threads by Python's GIL — 7x performance penalty.
        with open(image_path, 'rb') as f:
            file_data = f.read()

        content_type_mime = mimetypes.guess_type(image_path)[0] or 'image/jpeg'

        # Batch upload_id: create_gallery starts a new batch,
        # subsequent images reuse it. This is how Turbo groups images
        # into a gallery — all images with the same upload_id.
        if create_gallery:
            self._batch_upload_id = ''.join(
                random.choices(string.ascii_lowercase + string.digits, k=20)
            )

        upload_id = self._batch_upload_id or ''.join(
            random.choices(string.ascii_lowercase + string.digits, k=20)
        )

        curl = self._get_thread_curl()
        response_buffer = BytesIO()

        try:
            with self._upload_count_lock:
                self._upload_count += 1

            curl.setopt(pycurl.URL, self.upload_url)
            curl.setopt(pycurl.WRITEDATA, response_buffer)

            if self.upload_read_timeout:
                curl.setopt(pycurl.TIMEOUT, self.upload_read_timeout)

            # Progress callback for bandwidth tracking
            if progress_callback:
                curl.setopt(pycurl.NOPROGRESS, False)
                curl.setopt(pycurl.XFERINFOFUNCTION,
                            lambda dltotal, dlnow, ultotal, ulnow: progress_callback(int(ulnow), int(ultotal)))

            curl.setopt(pycurl.HTTPHEADER, [
                'X-Requested-With: XMLHttpRequest',
                f'Referer: {self.base_url}',
                'Accept: */*',
            ])

            self._set_cookies(curl)

            # Upload from memory buffer (not disk) for true concurrent uploads
            form_fields = [
                ('qqfile', (pycurl.FORM_BUFFER, filename,
                            pycurl.FORM_BUFFERPTR, file_data,
                            pycurl.FORM_CONTENTTYPE, content_type_mime)),
                ('upload_id', upload_id),
                ('thumb_size', str(thumbnail_size)),
                ('imcontent', content_type),
            ]

            if self._batch_upload_id and gallery_name:
                form_fields.append(('galleryAN', '1'))
                form_fields.append(('galleryN', gallery_name))
            elif create_gallery and gallery_name:
                form_fields.append(('galleryAN', '1'))
                form_fields.append(('galleryN', gallery_name))

            upload_start = time.time()

            curl.setopt(pycurl.HTTPPOST, form_fields)
            curl.perform()

            response_code = curl.getinfo(pycurl.RESPONSE_CODE)
            upload_time = time.time() - upload_start

            if response_code != 200:
                raise Exception(f"Upload failed with status {response_code}")

            response_text = response_buffer.getvalue().decode('utf-8')

            try:
                upload_json = json.loads(response_text)
            except json.JSONDecodeError:
                raise Exception(f"Upload response is not JSON: {response_text[:200]}")

            if not upload_json.get('success'):
                raise Exception(f"Upload rejected by server: {response_text[:200]}")

            result = self.normalize_response(
                status='success',
                original_filename=filename,
                gallery_id=self._batch_upload_id,
            )

            result['upload_time'] = upload_time
            result['file_size'] = os.path.getsize(image_path)

            log(f"Uploaded {filename} to TurboImageHost in {upload_time:.2f}s",
                level="debug", category="uploads")

            return result

        except pycurl.error as e:
            # Connection died — kill the handle so next call gets a fresh one
            self._thread_local.curl = None
            try:
                curl.close()
            except Exception:
                pass
            err_code, err_msg = e.args if len(e.args) == 2 else (0, str(e))
            log(f"TurboImageHost pycurl error {err_code}: {err_msg}", level="error", category="uploads")
            raise Exception(f"Upload error (pycurl {err_code}): {err_msg}")
        except Exception as e:
            log(f"TurboImageHost upload error: {e}", level="error", category="uploads")
            raise

    def _parse_result_page(self, html: str, filename: str) -> Dict[str, Any]:
        """Parse TurboImageHost upload result page (html5_upload_result.tu).

        Handles two layouts:
        - Single image: BBCode in <input id="imgCodeIPF" value="...">
        - Multiple images: BBCode in <textarea id="imgCodeURF">...</textarea>
        - Gallery URL always in <input id="imgCodeGG" value="..."> when present
        """
        result: Dict[str, Any] = {
            'success': False,
            'image_url': None,
            'thumbnail_url': None,
            'gallery_id': None,
            'bbcode': None,
        }

        # Gallery URL
        gallery_match = re.search(
            r'<input[^>]*id="imgCodeGG"[^>]*value="([^"]*)"',
            html, re.IGNORECASE,
        )
        if gallery_match:
            album_match = re.search(r'/album/(\d+)', gallery_match.group(1))
            if album_match:
                result['gallery_id'] = album_match.group(1)

        # Single-image: <input id="imgCodeIPF" value="...">
        bbcode_input = re.search(
            r'<input[^>]*id="imgCodeIPF"[^>]*value="([^"]+)"',
            html, re.IGNORECASE,
        )
        if bbcode_input:
            bbcode = bbcode_input.group(1).strip()
            if bbcode:
                result['bbcode'] = bbcode
                url_match = re.search(
                    r'\[URL=([^\]]+)\]\[IMG\]([^\[]+)\[/IMG\]\[/URL\]',
                    bbcode, re.IGNORECASE,
                )
                if url_match:
                    result['image_url'] = url_match.group(1)
                    result['thumbnail_url'] = url_match.group(2)
                result['success'] = True
                return result

        # Multi-image: <textarea id="imgCodeURF">...</textarea>
        textarea_match = re.search(
            r'<textarea[^>]*id="imgCodeURF"[^>]*>(.*?)</textarea>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if textarea_match:
            entries = re.findall(
                r'\[URL=[^\]]+\]\[IMG\][^\[]+\[/IMG\]\[/URL\]',
                textarea_match.group(1), re.IGNORECASE,
            )
            if entries:
                matched = None
                for entry in entries:
                    if filename.lower() in entry.lower():
                        matched = entry
                        break
                if not matched:
                    matched = entries[-1]

                result['bbcode'] = matched
                url_match = re.search(
                    r'\[URL=([^\]]+)\]\[IMG\]([^\[]+)\[/IMG\]\[/URL\]',
                    matched, re.IGNORECASE,
                )
                if url_match:
                    result['image_url'] = url_match.group(1)
                    result['thumbnail_url'] = url_match.group(2)
                result['success'] = True
                return result

        # Fallback: thumbnail divs
        div_match = re.search(
            r'<div[^>]*id="im_\d+"[^>]*title="' + re.escape(filename) + r'"[^>]*>'
            r'<a[^>]*href="([^"]+)"[^>]*class="thumbUrl"[^>]*'
            r"style=\"background-image:url\('([^']+)'\)\"",
            html, re.IGNORECASE,
        )
        if div_match:
            result['image_url'] = div_match.group(1)
            result['thumbnail_url'] = div_match.group(2)
            result['bbcode'] = f"[URL={result['image_url']}][IMG]{result['thumbnail_url']}[/IMG][/URL]"
            result['success'] = True

        return result

    def fetch_batch_results(self, max_retries: int = 3) -> Dict[str, Any]:
        """Fetch the result page ONCE after all uploads and parse all BBCode.

        Called by the engine after the upload loop completes.
        Retries on failure since this is the only source of image URLs/BBCode.
        Returns {gallery_id, images: [{original_filename, image_url, thumb_url, bbcode}, ...]}
        """
        if not self._batch_upload_id:
            return {'gallery_id': None, 'images': []}

        result_url = (
            f"{self.base_url}/html5_upload_result.tu"
            f"?upload_id={self._batch_upload_id}"
        )

        for attempt in range(max_retries):
            curl = pycurl.Curl()
            response_buffer = BytesIO()
            try:
                curl.setopt(pycurl.URL, result_url)
                curl.setopt(pycurl.WRITEDATA, response_buffer)
                self._configure_curl(curl)
                if self.upload_read_timeout:
                    curl.setopt(pycurl.TIMEOUT, self.upload_read_timeout)
                self._set_cookies(curl)

                curl.perform()

                response_code = curl.getinfo(pycurl.RESPONSE_CODE)
                if response_code != 200:
                    log(f"Batch results fetch attempt {attempt + 1}/{max_retries} failed: status {response_code}",
                        level="warning", category="uploads")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return {'gallery_id': None, 'images': []}

                html = response_buffer.getvalue().decode('utf-8', errors='replace')
                batch = self._parse_batch_html(html)

                log(f"Batch results: {len(batch['images'])} images, gallery_id={batch['gallery_id']}",
                    level="debug", category="uploads")
                return batch

            except pycurl.error as e:
                log(f"Batch results fetch attempt {attempt + 1}/{max_retries} failed (pycurl): {e}",
                    level="warning", category="uploads")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return {'gallery_id': None, 'images': []}
            except Exception as e:
                log(f"Batch results fetch attempt {attempt + 1}/{max_retries} failed: {e}",
                    level="warning", category="uploads")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return {'gallery_id': None, 'images': []}
            finally:
                curl.close()

        return {'gallery_id': None, 'images': []}

    def _parse_batch_html(self, html: str) -> Dict[str, Any]:
        """Parse batch result HTML into structured data."""
        batch: Dict[str, Any] = {'gallery_id': None, 'images': []}

        # Gallery URL
        gallery_match = re.search(
            r'<input[^>]*id="imgCodeGG"[^>]*value="([^"]*)"',
            html, re.IGNORECASE,
        )
        if gallery_match:
            album_match = re.search(r'/album/(\d+)', gallery_match.group(1))
            if album_match:
                batch['gallery_id'] = album_match.group(1)

        # Per-image data from thumbnail divs
        div_pattern = re.compile(
            r'<div[^>]*id="im_(\d+)"[^>]*title="([^"]*)"[^>]*>'
            r'<a[^>]*href="([^"]+)"[^>]*class="thumbUrl"[^>]*'
            r"style=\"background-image:url\('([^']+)'\)\"",
            re.IGNORECASE,
        )
        div_images = {}
        for m in div_pattern.finditer(html):
            img_id, fname, image_url, thumb_url = m.group(1), m.group(2), m.group(3), m.group(4)
            div_images[fname.lower()] = {
                'original_filename': fname,
                'image_url': image_url,
                'thumb_url': thumb_url,
                'bbcode': f"[URL={image_url}][IMG]{thumb_url}[/IMG][/URL]",
            }

        # Server-generated BBCode from textarea or input
        bbcode_by_file: Dict[str, str] = {}

        textarea_match = re.search(
            r'<textarea[^>]*id="imgCodeURF"[^>]*>(.*?)</textarea>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if textarea_match:
            entries = re.findall(
                r'\[URL=[^\]]+\]\[IMG\][^\[]+\[/IMG\]\[/URL\]',
                textarea_match.group(1), re.IGNORECASE,
            )
            for entry in entries:
                for fname_lower in div_images:
                    if fname_lower in entry.lower():
                        bbcode_by_file[fname_lower] = entry
                        break
        else:
            input_match = re.search(
                r'<input[^>]*id="imgCodeIPF"[^>]*value="([^"]+)"',
                html, re.IGNORECASE,
            )
            if input_match:
                bbcode = input_match.group(1).strip()
                if bbcode and div_images:
                    only_key = next(iter(div_images))
                    bbcode_by_file[only_key] = bbcode

        # Merge
        for fname_lower, div_data in div_images.items():
            if fname_lower in bbcode_by_file:
                server_bb = bbcode_by_file[fname_lower]
                div_data['bbcode'] = server_bb
                url_match = re.search(
                    r'\[URL=([^\]]+)\]\[IMG\]([^\[]+)\[/IMG\]\[/URL\]',
                    server_bb, re.IGNORECASE,
                )
                if url_match:
                    div_data['image_url'] = url_match.group(1)
                    div_data['thumb_url'] = url_match.group(2)
            batch['images'].append(div_data)

        return batch

    def get_gallery_url(self, gallery_id: str, gallery_name: str = "") -> str:
        """Get the gallery URL for TurboImageHost."""
        if gallery_name:
            safe_name = gallery_name.replace(' ', '_')
            return f"{self.base_url}/album/{gallery_id}/{safe_name}"
        else:
            return f"{self.base_url}/album/{gallery_id}"

    def get_thumbnail_url(self, img_id: str, ext: str = "") -> str:
        """Get the thumbnail URL for a given image ID."""
        return f"https://s8d8.turboimg.net/t1/{img_id}{ext}"

    def sanitize_gallery_name(self, name: str) -> str:
        """TurboImageHost gallery name rules: max 20 chars, spaces to underscores."""
        if not name:
            return 'untitled'
        sanitized = re.sub(r'[^\w\s\-.]', '', name)
        sanitized = sanitized.strip()[:20]
        return sanitized or 'untitled'

    def get_default_headers(self) -> dict:
        """Return default headers for TurboImageHost."""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': self.base_url,
        }

    def clear_api_cookies(self):
        """Clear batch state for new gallery uploads. Preserve session cookie."""
        self._batch_upload_id = None
        log("TurboImageHost batch state cleared", level="debug", category="network")
