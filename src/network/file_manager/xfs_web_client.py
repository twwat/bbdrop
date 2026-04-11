"""Shared base class for XFS (XFileSharing Pro) web-panel file managers.

Filedot and Filespace both run XFS but have NOT enabled the JSON API
mod, so all file management operations go through the web panel using
the session already maintained by the upload worker's FileHostClient.

This module hoists the shared scraping, form-building, and request
dispatch logic so each subclass only provides:

- class constants: BASE_URL, LINK_PREFIX, USES_CSRF_TOKEN, regexes,
  stale-token markers
- URL builder hooks: _folder_url, _file_edit_url, _fld_edit_url,
  _delete_file_url, _delete_folder_url
- flag-toggle request shape: _build_flag_requests (Filedot batches;
  Filespace sends per-file GETs)
- get_account_info (host-specific selectors)

Two id types matter for every XFS host:
- file_code: alphanumeric, used in file URLs, stored in the DB,
  passed through as FileInfo.id
- file_id:   numeric, used by the action-panel form and flag AJAX.
  _scrape_page populates self._file_code_to_numeric as a per-folder
  cache so mutating ops can translate back.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlencode

from src.network.file_host_client import FileHostClient
from src.network.file_manager.client import (
    BatchResult,
    FileInfo,
    FileListResult,
    FileManagerCapabilities,
    FileManagerClient,
    FolderListResult,
    OperationResult,
)
from src.utils.logger import log

# ---------------------------------------------------------------------------
# Shared regexes — same XFS /file_edit form layout on both hosts
# ---------------------------------------------------------------------------

_FILE_EDIT_INPUT_RE = re.compile(
    r'<input[^>]*\bname="(?P<name>file_name|file_password|file_price)"'
    r'[^>]*\bvalue="(?P<value>[^"]*)"',
    re.IGNORECASE,
)
_FILE_EDIT_TEXTAREA_RE = re.compile(
    r'<textarea[^>]*\bname="(?P<name>file_descr)"[^>]*>'
    r'(?P<value>.*?)</textarea>',
    re.DOTALL | re.IGNORECASE,
)
_FILE_EDIT_CHECKBOX_RE = re.compile(
    r'<input[^>]*\bname="(?P<name>file_public|file_premium_only)"[^>]*>',
    re.IGNORECASE,
)
_CHECKED_RE = re.compile(r'\bchecked\b', re.IGNORECASE)

_FILE_EDIT_FIELDS = (
    "file_name", "file_descr", "file_password", "file_price",
    "file_public", "file_premium_only",
)

# Size parsing
_SIZE_MULTIPLIERS = {
    "B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4,
}


def _parse_size(size_str: str) -> int:
    """Parse '2.4 GB' or '890 MB' to bytes."""
    size_str = size_str.strip().upper()
    for suffix, mult in sorted(
        _SIZE_MULTIPLIERS.items(), key=lambda x: -len(x[0])
    ):
        if size_str.endswith(suffix):
            try:
                return int(float(size_str[:-len(suffix)].strip()) * mult)
            except ValueError:
                return 0
    return 0


class XFSWebFileManagerBase(FileManagerClient):
    """Shared base for XFS web-panel file manager clients.

    Subclasses MUST set class-level constants BASE_URL, LINK_PREFIX,
    USES_CSRF_TOKEN, _FILE_ROW_RE, _FOLDER_ROW_RE, _STALE_TOKEN_MARKERS
    and implement the URL builder hooks and _build_flag_requests.
    """

    # ---- Subclass-provided class constants --------------------------------
    BASE_URL: str = ""
    LINK_PREFIX: str = ""
    USES_CSRF_TOKEN: bool = False
    _FILE_ROW_RE: re.Pattern = re.compile(r"$.")  # never matches
    _FOLDER_ROW_RE: re.Pattern = re.compile(r"$.")
    _STALE_TOKEN_MARKERS: tuple = ()
    # Token source in page HTML — subclasses that use tokens override this.
    _TOKEN_RE: re.Pattern = re.compile(r"$.")
    _HIDDEN_TOKEN_INPUT_RE: re.Pattern = re.compile(r"$.")

    # ---- Construction -----------------------------------------------------

    def __init__(self, file_host_client: FileHostClient, timeout: int = 30):
        """
        Args:
            file_host_client: The upload worker's FileHostClient for this
                host. All HTTP requests go through it, inheriting proxy,
                bandwidth counter, session cookies, and reauth.
            timeout: Per-request timeout in seconds.
        """
        self._http = file_host_client
        self.timeout = timeout
        self._action_token: str = ""
        self._file_code_to_numeric: Dict[str, str] = {}
        self._known_folder_ids: Set[str] = set()
        self._last_folder_id: str = ""
        self._last_list_fld_id: str = "0"

    # ---- HTTP plumbing ----------------------------------------------------

    def _web_get(self, url: str) -> str:
        _status, _headers, body = self._http.request(
            "GET", url, timeout=self.timeout
        )
        return body.decode("utf-8", errors="replace")

    def _web_post(
        self,
        url: str,
        fields: Optional[Dict[str, str]] = None,
        *,
        body: Optional[bytes] = None,
    ) -> str:
        if body is None:
            if fields is None:
                raise ValueError("_web_post requires fields or body")
            body = urlencode(fields).encode("utf-8")
        _status, _headers, resp = self._http.request(
            "POST",
            url,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        return resp.decode("utf-8", errors="replace")

    # ---- URL builder hooks (subclasses override) --------------------------

    def _folder_url(self, folder_id: str, page: int = 1) -> str:
        raise NotImplementedError

    def _file_edit_url(self, file_code: str) -> str:
        raise NotImplementedError

    def _fld_edit_url(self, fld_id: str) -> str:
        raise NotImplementedError

    def _delete_file_url(self, file_code: str) -> str:
        raise NotImplementedError

    def _delete_folder_url(self, fld_id: str) -> str:
        raise NotImplementedError

    def _action_form_url(self) -> str:
        """URL for the shared action-panel form (create/move/copy/flags)."""
        return f"{self.BASE_URL}/"

    # ---- Token helpers ----------------------------------------------------

    def _token_field(self) -> Dict[str, str]:
        if self.USES_CSRF_TOKEN and self._action_token:
            return {"token": self._action_token}
        return {}

    def _is_stale_token_response(self, body: str) -> bool:
        if not self.USES_CSRF_TOKEN or not self._STALE_TOKEN_MARKERS:
            return False
        low = body.lower()
        return any(m.lower() in low for m in self._STALE_TOKEN_MARKERS)

    def _ensure_token(self) -> None:
        if not self.USES_CSRF_TOKEN:
            return
        if self._action_token and self._file_code_to_numeric is not None:
            return
        self._scrape_page(self._last_folder_id or "/", 1)

    # ---- Scraping ---------------------------------------------------------

    def _scrape_page(self, folder_id: str, page: int) -> Tuple[list, list]:
        html = self._web_get(self._folder_url(folder_id, page))

        if self.USES_CSRF_TOKEN:
            token_match = self._TOKEN_RE.search(html)
            if token_match:
                self._action_token = token_match.group(1)

        self._file_code_to_numeric = {}
        self._known_folder_ids = set()
        self._last_folder_id = folder_id
        self._last_list_fld_id = (
            folder_id if folder_id and folder_id not in ("/", "") else "0"
        )

        folders = []
        for match in self._FOLDER_ROW_RE.finditer(html):
            fld_id = match.group(1)
            raw_name = match.group(2)
            name = re.sub(r'<[^>]+>', '', raw_name).strip()
            self._known_folder_ids.add(fld_id)
            folders.append(FileInfo(
                id=fld_id,
                name=name or fld_id,
                is_folder=True,
                parent_id=folder_id if folder_id not in ("/", "") else None,
            ))

        files = []
        for match in self._FILE_ROW_RE.finditer(html):
            numeric_id = match.group(1)
            file_code = match.group(2)
            raw_name = match.group(3)
            name = re.sub(r'<[^>]+>', '', raw_name).strip()
            size_str = match.group(4)
            self._file_code_to_numeric[file_code] = numeric_id
            files.append(FileInfo(
                id=file_code,
                name=name or file_code,
                is_folder=False,
                size=_parse_size(size_str),
                is_available=True,
                parent_id=folder_id if folder_id not in ("/", "") else None,
            ))

        log(f"{self.BASE_URL} scraped folder_id={folder_id!r} page={page}: "
            f"{len(folders)} folders, {len(files)} files "
            f"(token_cached={bool(self._action_token)}, "
            f"numeric_ids={len(self._file_code_to_numeric)})",
            level="debug", category="file_manager")

        return folders, files

    def _resolve_numeric_ids(
        self, file_codes: List[str]
    ) -> Tuple[List[str], List[str]]:
        if not file_codes:
            return [], []

        needs_reprime = any(
            code not in self._file_code_to_numeric for code in file_codes
        )
        if needs_reprime:
            try:
                self._scrape_page(self._last_folder_id or "/", 1)
            except Exception as e:
                log(f"{self.BASE_URL}: failed to re-prime numeric id cache: {e}",
                    level="warning", category="file_manager")

        numerics: List[str] = []
        missing: List[str] = []
        for code in file_codes:
            num = self._file_code_to_numeric.get(code)
            if num:
                numerics.append(num)
            else:
                missing.append(code)
        return numerics, missing

    # ---- FileManagerClient implementations --------------------------------

    def list_files(
        self,
        folder_id: str = "/",
        page: int = 1,
        per_page: int = 50,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> FileListResult:
        folders, files = self._scrape_page(folder_id, page)
        items = folders + files
        return FileListResult(
            files=items, total=len(items), page=page, per_page=per_page,
        )

    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        folders, _files = self._scrape_page(parent_id, page=1)
        return FolderListResult(
            folders=folders, breadcrumb=[(parent_id, parent_id)]
        )

    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        self._ensure_token()
        if self.USES_CSRF_TOKEN and not self._action_token:
            return OperationResult(
                success=False,
                message=f"Could not prime action token for {self.BASE_URL}",
            )

        parent_fld = (
            parent_id if parent_id and parent_id not in ("/", "") else "0"
        )
        fields = {
            "op": "my_files",
            **self._token_field(),
            "fld_id": parent_fld,
            "create_new_folder": name,
            "create_folder_submit": "Create Folder",
        }

        try:
            resp = self._web_post(self._action_form_url(), fields)
        except Exception as e:
            return OperationResult(success=False, message=str(e))

        if self._is_stale_token_response(resp):
            self._action_token = ""
            return OperationResult(
                success=False,
                message="CSRF token rotated — refresh the folder and retry",
            )

        return OperationResult(
            success=True,
            message=f"Folder '{name}' created",
            data={"name": name, "parent_id": parent_fld},
        )

    def rename(self, item_id: str, new_name: str) -> OperationResult:
        self._ensure_token()
        if self.USES_CSRF_TOKEN and not self._action_token:
            return OperationResult(
                success=False,
                message=f"Could not prime action token for {self.BASE_URL}",
            )

        is_folder = item_id in self._known_folder_ids

        if is_folder:
            url = self._fld_edit_url(item_id)
            fields = {
                "op": "fld_edit",
                "fld_id": item_id,
                "fld_name": new_name,
                **self._token_field(),
                "save": "Save",
            }
        else:
            url = self._file_edit_url(item_id)
            fields = {
                "op": "file_edit",
                "file_code": item_id,
                "file_name": new_name,
                **self._token_field(),
                "save": "Save",
            }

        try:
            resp = self._web_post(url, fields)
        except Exception as e:
            return OperationResult(success=False, message=str(e))

        if self._is_stale_token_response(resp):
            self._action_token = ""
            return OperationResult(
                success=False,
                message="CSRF token rotated — refresh the folder and retry",
            )

        return OperationResult(success=True, message="Renamed")

    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        return self._action_panel_bulk(
            item_ids, dest_folder_id,
            action_field="to_folder_move", action_value="Move files",
        )

    def copy(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        return self._action_panel_bulk(
            item_ids, dest_folder_id,
            action_field="to_folder_copy", action_value="Copy files",
        )

    def _action_panel_bulk(
        self,
        item_ids: List[str],
        dest_folder_id: str,
        *,
        action_field: str,
        action_value: str,
    ) -> BatchResult:
        self._ensure_token()
        if self.USES_CSRF_TOKEN and not self._action_token:
            return BatchResult(
                succeeded=[],
                failed=[(i, "failed to prime action token") for i in item_ids],
            )

        numerics, missing = self._resolve_numeric_ids(item_ids)
        if not numerics:
            return BatchResult(
                succeeded=[],
                failed=[(c, "no numeric id for file_code") for c in missing],
            )

        dest_fld = (
            dest_folder_id
            if dest_folder_id and dest_folder_id not in ("/", "")
            else "0"
        )

        fields: list = [("op", "my_files")]
        if self.USES_CSRF_TOKEN and self._action_token:
            fields.append(("token", self._action_token))
        fields.extend([
            ("fld_id", self._last_list_fld_id),
            ("to_folder", dest_fld),
            (action_field, action_value),
        ])
        for num in numerics:
            fields.append(("file_id", num))

        body = urlencode(fields).encode("utf-8")

        try:
            resp = self._web_post(self._action_form_url(), body=body)
        except Exception as e:
            return BatchResult(
                succeeded=[],
                failed=[(c, str(e)) for c in item_ids],
            )

        if self._is_stale_token_response(resp):
            self._action_token = ""
            return BatchResult(
                succeeded=[],
                failed=[(c, "CSRF token rotated") for c in item_ids],
            )

        resolved_codes = [
            c for c in item_ids if c in self._file_code_to_numeric
        ]
        return BatchResult(
            succeeded=resolved_codes,
            failed=[(c, "no numeric id for file_code") for c in missing],
        )

    def delete(self, item_ids: List[str]) -> BatchResult:
        self._ensure_token()
        if self.USES_CSRF_TOKEN and not self._action_token:
            return BatchResult(
                succeeded=[],
                failed=[(i, "failed to prime action token") for i in item_ids],
            )

        succeeded: list = []
        failed: list = []

        for item_id in item_ids:
            try:
                if item_id in self._known_folder_ids:
                    url = self._delete_folder_url(item_id)
                else:
                    url = self._delete_file_url(item_id)
                resp = self._web_get(url)
                if self._is_stale_token_response(resp):
                    self._action_token = ""
                    failed.append((item_id, "CSRF token rotated"))
                else:
                    succeeded.append(item_id)
            except Exception as e:
                failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    # ---- Flag toggles (POST / GET shape is subclass-specific) -------------

    def set_file_public(
        self, item_ids: List[str], value: bool
    ) -> BatchResult:
        return self._set_file_flag(item_ids, "file_public", value)

    def set_file_premium(
        self, item_ids: List[str], value: bool
    ) -> BatchResult:
        return self._set_file_flag(item_ids, "file_premium_only", value)

    def _set_file_flag(
        self, item_ids: List[str], flag_name: str, value: bool
    ) -> BatchResult:
        self._ensure_token()
        if self.USES_CSRF_TOKEN and not self._action_token:
            return BatchResult(
                succeeded=[],
                failed=[(i, "failed to prime action token") for i in item_ids],
            )

        numerics, missing = self._resolve_numeric_ids(item_ids)
        if not numerics:
            return BatchResult(
                succeeded=[],
                failed=[(c, "no numeric id for file_code") for c in missing],
            )

        requests = self._build_flag_requests(numerics, flag_name, value)

        stale = False
        error: Optional[str] = None
        for method, url, body in requests:
            try:
                if method == "POST":
                    _s, _h, resp_bytes = self._http.request(
                        "POST", url,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        body=body, timeout=self.timeout,
                    )
                else:
                    _s, _h, resp_bytes = self._http.request(
                        "GET", url, timeout=self.timeout,
                    )
                resp = resp_bytes.decode("utf-8", errors="replace")
                if self._is_stale_token_response(resp):
                    stale = True
                    break
            except Exception as e:
                error = str(e)
                break

        if stale:
            self._action_token = ""
            return BatchResult(
                succeeded=[],
                failed=[(c, "CSRF token rotated") for c in item_ids],
            )
        if error is not None:
            return BatchResult(
                succeeded=[],
                failed=[(c, error) for c in item_ids],
            )

        resolved_codes = [
            c for c in item_ids if c in self._file_code_to_numeric
        ]
        return BatchResult(
            succeeded=resolved_codes,
            failed=[(c, "no numeric id for file_code") for c in missing],
        )

    def _build_flag_requests(
        self,
        numeric_ids: List[str],
        flag_name: str,
        value: bool,
    ) -> List[Tuple[str, str, Optional[bytes]]]:
        """Return (method, url, body) tuples for a flag-toggle operation.

        Filedot returns a single POST with all file_ids batched.
        Filespace returns one GET per file_id.
        """
        raise NotImplementedError

    # ---- File-edit properties (XFS form layout is shared) -----------------

    def read_file_properties(self, file_code: str) -> Dict[str, str]:
        url = self._file_edit_url(file_code)
        html = self._web_get(url)

        if self.USES_CSRF_TOKEN:
            token_match = self._HIDDEN_TOKEN_INPUT_RE.search(html)
            if token_match:
                self._action_token = token_match.group(1)

        values: Dict[str, str] = {f: "" for f in _FILE_EDIT_FIELDS}
        values["file_public"] = "0"
        values["file_premium_only"] = "0"

        for match in _FILE_EDIT_INPUT_RE.finditer(html):
            values[match.group("name")] = match.group("value")

        for match in _FILE_EDIT_TEXTAREA_RE.finditer(html):
            values[match.group("name")] = match.group("value")

        for match in _FILE_EDIT_CHECKBOX_RE.finditer(html):
            tag = match.group(0)
            values[match.group("name")] = "1" if _CHECKED_RE.search(tag) else "0"

        return values

    def update_file_properties(
        self,
        file_codes: List[str],
        fields: Dict[str, str],
        *,
        round_trip: bool = True,
    ) -> BatchResult:
        self._ensure_token()
        if self.USES_CSRF_TOKEN and not self._action_token:
            return BatchResult(
                succeeded=[],
                failed=[(c, "failed to prime action token") for c in file_codes],
            )

        succeeded: list = []
        failed: list = []
        single = len(file_codes) == 1 and round_trip

        for idx, code in enumerate(file_codes):
            url = self._file_edit_url(code)
            try:
                if single:
                    current = self.read_file_properties(code)
                    merged = dict(current)
                    merged.update(fields)
                else:
                    merged = {
                        k: v for k, v in fields.items()
                        if k != "file_name"
                    }

                post_fields = {
                    "op": "file_edit",
                    "file_code": code,
                    **self._token_field(),
                    "save": "Save",
                }
                post_fields.update(merged)

                resp = self._web_post(url, post_fields)
                if self._is_stale_token_response(resp):
                    self._action_token = ""
                    failed.append((code, "CSRF token rotated"))
                    for remaining in file_codes[idx + 1:]:
                        failed.append(
                            (remaining, "skipped: CSRF token rotated")
                        )
                    break
                succeeded.append(code)
            except Exception as e:
                failed.append((code, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def get_info(self, item_ids: List[str]) -> List[FileInfo]:
        return [
            FileInfo(id=fid, name=fid, is_folder=False) for fid in item_ids
        ]

    def get_download_link(self, file_id: str) -> str:
        return f"{self.LINK_PREFIX}{file_id}"
