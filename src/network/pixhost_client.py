"""
Pixhost client for image uploads.

Implements ImageHostClient for pixhost.to with:
- Variable thumbnail sizes (150-500px)
- Content type selection (family/adult)
- Gallery support via JSON API
- No authentication required
"""

import os
import json
import time
import mimetypes
import threading
from io import BytesIO
from typing import Dict, Any, Optional, Callable

import pycurl
import certifi

from src.core.image_host_config import (
    ImageHostConfig,
    get_image_host_config_manager,
    get_image_host_setting,
)
from src.network.image_host_client import ImageHostClient
from src.proxy.models import ProxyEntry
from src.utils.logger import log


class PixhostClient(ImageHostClient):
    """Client for Pixhost uploads via pycurl."""

    worker_thread: Optional[Any] = None

    def __init__(self, proxy: Optional[ProxyEntry] = None):
        _cfg = get_image_host_config_manager().get_host('pixhost')
        if _cfg is None:
            _cfg = ImageHostConfig(name="Pixhost", host_id="pixhost")
        super().__init__(_cfg, proxy=proxy)

        self.api_url = "https://api.pixhost.to"
        self._web_url = "https://pixhost.to"

        self.upload_connect_timeout = get_image_host_setting('pixhost', 'upload_connect_timeout', 'int')
        self.upload_read_timeout = get_image_host_setting('pixhost', 'upload_read_timeout', 'int')

        self._upload_count = 0
        self._upload_count_lock = threading.Lock()

        # Batch gallery tracking
        self._gallery_hash: Optional[str] = None
        self._gallery_upload_hash: Optional[str] = None

        self._thread_local = threading.local()

    def _get_thread_curl(self) -> pycurl.Curl:
        """Get or create a pycurl handle for the current thread."""
        curl = getattr(self._thread_local, 'curl', None)
        if curl is None:
            curl = pycurl.Curl()
            curl.setopt(pycurl.NOSIGNAL, 1)
            self._thread_local.curl = curl
        curl.reset()
        curl.setopt(pycurl.NOSIGNAL, 1)
        curl.setopt(pycurl.CAINFO, certifi.where())
        curl.setopt(pycurl.SSL_VERIFYPEER, 1)
        curl.setopt(pycurl.SSL_VERIFYHOST, 2)
        curl.setopt(pycurl.USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0')
        if self.upload_connect_timeout:
            curl.setopt(pycurl.CONNECTTIMEOUT, self.upload_connect_timeout)
        if self.proxy:
            from src.proxy.pycurl_adapter import PyCurlProxyAdapter
            PyCurlProxyAdapter.configure_proxy(curl, self.proxy)
        return curl

    @property
    def web_url(self) -> str:
        return self._web_url

    @property
    def host_id(self) -> str:
        return "pixhost"

    def login(self, username: str, password: str) -> bool:
        """Pixhost does not support authentication."""
        return True

    def create_gallery(self, name: str) -> str:
        """Create a new gallery on Pixhost and store its hash."""
        sanitized = self.sanitize_gallery_name(name)
        curl = self._get_thread_curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, f"{self.api_url}/galleries")
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.POST, 1)

            import urllib.parse
            post_data = f"name={urllib.parse.quote(sanitized)}"
            curl.setopt(pycurl.POSTFIELDS, post_data)

            curl.setopt(pycurl.HTTPHEADER, [
                'Content-Type: application/x-www-form-urlencoded',
                'Accept: application/json'
            ])

            curl.perform()
            response_code = curl.getinfo(pycurl.RESPONSE_CODE)

            if response_code != 200:
                raise RuntimeError(f"Gallery creation failed with status {response_code}")

            response_text = response_buffer.getvalue().decode('utf-8')
            json_resp = json.loads(response_text)
            
            self._gallery_hash = json_resp.get('gallery_hash')
            self._gallery_upload_hash = json_resp.get('gallery_upload_hash')
            
            if not self._gallery_hash:
                raise RuntimeError("Could not find gallery_hash in response")

            log(f"Created Pixhost gallery: {self._gallery_hash}", level="debug", category="uploads")
            return self._gallery_hash
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
        """Upload a single image to Pixhost via pycurl."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        content_type = get_image_host_setting('pixhost', 'content_type', 'str') or '0'
        thumbnail_size = max(150, min(500, thumbnail_size))
        filename = os.path.basename(image_path)

        with open(image_path, 'rb') as f:
            file_data = f.read()

        content_type_mime = mimetypes.guess_type(image_path)[0] or 'image/jpeg'

        if create_gallery and not self._gallery_hash:
            if gallery_name:
                self.create_gallery(gallery_name)
            else:
                self.create_gallery("untitled")

        curl = self._get_thread_curl()
        response_buffer = BytesIO()

        try:
            with self._upload_count_lock:
                self._upload_count += 1

            curl.setopt(pycurl.URL, f"{self.api_url}/images")
            curl.setopt(pycurl.WRITEDATA, response_buffer)

            if self.upload_read_timeout:
                curl.setopt(pycurl.TIMEOUT, self.upload_read_timeout)

            if progress_callback:
                curl.setopt(pycurl.NOPROGRESS, False)
                curl.setopt(pycurl.XFERINFOFUNCTION,
                            lambda dltotal, dlnow, ultotal, ulnow: progress_callback(int(ulnow), int(ultotal)))

            curl.setopt(pycurl.HTTPHEADER, ['Accept: application/json'])

            form_fields = [
                ('img', (pycurl.FORM_BUFFER, filename,
                         pycurl.FORM_BUFFERPTR, file_data,
                         pycurl.FORM_CONTENTTYPE, content_type_mime)),
                ('content_type', content_type),
                ('max_th_size', str(thumbnail_size)),
            ]

            if self._gallery_hash and self._gallery_upload_hash:
                form_fields.append(('gallery_hash', self._gallery_hash))
                form_fields.append(('gallery_upload_hash', self._gallery_upload_hash))
            elif gallery_id:
                # If we resume to an existing gallery, we might not have upload_hash anymore,
                # but Pixhost API implies gallery_upload_hash is required for /images.
                # It's only valid for 24h anyway.
                form_fields.append(('gallery_hash', gallery_id))

            upload_start = time.time()
            curl.setopt(pycurl.HTTPPOST, form_fields)
            curl.perform()

            response_code = curl.getinfo(pycurl.RESPONSE_CODE)
            upload_time = time.time() - upload_start

            if response_code != 200:
                raise Exception(f"Upload failed with status {response_code}")

            response_text = response_buffer.getvalue().decode('utf-8')
            try:
                json_resp = json.loads(response_text)
            except json.JSONDecodeError:
                raise Exception(f"Upload response is not JSON: {response_text[:200]}")

            # Check for the "fake 200" response
            show_url = json_resp.get('show_url', '')
            th_url = json_resp.get('th_url', '')
            if show_url.endswith('/') or th_url.endswith('/'):
                # API issue: successfully returned 200 but image did not process properly
                action = get_image_host_setting('pixhost', 'error_retry_strategy', 'str') or 'retry_image'
                if action == 'retry_gallery':
                    # Signal full corruption to user
                    raise Exception(f"Gallery corrupted due to Pixhost internal error on {filename}. Zip download will fail. Clear gallery to retry all.")
                else:
                    raise Exception(f"Pixhost returned fake 200 response for {filename}")

            bbcode = f"[URL={show_url}][IMG]{th_url}[/IMG][/URL]"

            result = self.normalize_response(
                status='success',
                original_filename=filename,
                gallery_id=self._gallery_hash,
                image_url=show_url,
                thumb_url=th_url,
                bbcode=bbcode
            )

            result['upload_time'] = upload_time
            result['file_size'] = os.path.getsize(image_path)

            log(f"Uploaded {filename} to Pixhost in {upload_time:.2f}s", level="debug", category="uploads")
            return result

        except pycurl.error as e:
            self._thread_local.curl = None
            try:
                curl.close()
            except Exception:
                pass
            err_code, err_msg = e.args if len(e.args) == 2 else (0, str(e))
            log(f"Pixhost pycurl error {err_code}: {err_msg}", level="error", category="uploads")
            raise Exception(f"Upload error (pycurl {err_code}): {err_msg}")
        except Exception as e:
            log(f"Pixhost upload error: {e}", level="error", category="uploads")
            raise

    def fetch_batch_results(self, max_retries: int = 3) -> Dict[str, Any]:
        """Finalize the gallery batch after all images have uploaded."""
        if not self._gallery_hash:
            return {'gallery_id': None, 'images': []}

        # Auto-finalize check
        auto_finalize = get_image_host_setting('pixhost', 'auto_finalize_gallery', 'bool')
        if auto_finalize is False:
            log(f"Pixhost auto-finalize disabled for gallery {self._gallery_hash}", level="debug", category="uploads")
            return {'gallery_id': self._gallery_hash, 'images': []}

        curl = pycurl.Curl()
        response_buffer = BytesIO()
        try:
            curl.setopt(pycurl.URL, f"{self.api_url}/galleries/{self._gallery_hash}/finalize")
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.POST, 1)
            curl.setopt(pycurl.POSTFIELDS, "")
            curl.setopt(pycurl.HTTPHEADER, ['Accept: application/json'])
            
            curl.perform()
            response_code = curl.getinfo(pycurl.RESPONSE_CODE)
            
            if response_code == 200:
                log(f"Successfully finalized Pixhost gallery {self._gallery_hash}", level="info", category="uploads")
            else:
                log(f"Failed to finalize Pixhost gallery {self._gallery_hash}, status: {response_code}", level="warning", category="uploads")
        except Exception as e:
            log(f"Error finalizing Pixhost gallery: {e}", level="warning", category="uploads")
        finally:
            curl.close()

        return {'gallery_id': self._gallery_hash, 'images': []}

    def get_gallery_url(self, gallery_id: str, gallery_name: str = "") -> str:
        """Get the gallery URL for Pixhost."""
        return f"{self._web_url}/gallery/{gallery_id}"

    def get_thumbnail_url(self, img_id: str, ext: str = "") -> str:
        """Get the thumbnail URL. For offline cache only."""
        return f"https://t1.pixhost.to/thumbs/{img_id}{ext}"

    def sanitize_gallery_name(self, name: str) -> str:
        """Pixhost gallery name rules."""
        if not name:
            return 'untitled'
        sanitized = name.strip()[:100]
        return sanitized or 'untitled'

    def get_default_headers(self) -> dict:
        return {'Accept': 'application/json'}

    def upload_cover(self, image_path: str, gallery_id: str = "") -> Optional[dict]:
        """Upload a cover image to Pixhost's dedicated cover endpoint via pycurl."""
        if not os.path.exists(image_path):
            return None

        content_type = get_image_host_setting('pixhost', 'content_type', 'str') or '0'
        filename = os.path.basename(image_path)

        with open(image_path, 'rb') as f:
            file_data = f.read()

        content_type_mime = mimetypes.guess_type(image_path)[0] or 'image/jpeg'

        curl = self._get_thread_curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, f"{self.api_url}/covers")
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            
            if self.upload_read_timeout:
                curl.setopt(pycurl.TIMEOUT, self.upload_read_timeout)

            curl.setopt(pycurl.HTTPHEADER, ['Accept: application/json'])

            form_fields = [
                ('img_left', (pycurl.FORM_BUFFER, filename,
                         pycurl.FORM_BUFFERPTR, file_data,
                         pycurl.FORM_CONTENTTYPE, content_type_mime)),
                ('content_type', content_type),
            ]
            
            # Pixhost doesn't natively attach cover to a specific gallery via API (no parameter documented),
            # but we can provide the BBCode for it.

            curl.setopt(pycurl.HTTPPOST, form_fields)
            curl.perform()

            response_code = curl.getinfo(pycurl.RESPONSE_CODE)

            if response_code != 200:
                log(f"Cover upload failed with status {response_code}", level="warning", category="cover")
                return None

            response_text = response_buffer.getvalue().decode('utf-8')
            json_resp = json.loads(response_text)
            
            show_url = json_resp.get('show_url', '')
            th_url = json_resp.get('th_url', '')
            
            if show_url.endswith('/') or th_url.endswith('/'):
                 log(f"Cover upload returned fake 200 response", level="warning", category="cover")
                 return None

            bbcode = f"[URL={show_url}][IMG]{th_url}[/IMG][/URL]"

            log(f"Cover uploaded successfully to Pixhost", level="info", category="cover")
            return {
                "status": "success",
                "bbcode": bbcode,
                "image_url": show_url,
                "thumb_url": th_url,
            }

        except Exception as e:
            log(f"Pixhost cover upload error: {e}", level="error", category="cover")
            return None
        finally:
            curl.close()

    def clear_api_cookies(self):
        """Clear batch state for new gallery uploads."""
        self._gallery_hash = None
        self._gallery_upload_hash = None
        log("Pixhost batch state cleared", level="trace", category="network")
