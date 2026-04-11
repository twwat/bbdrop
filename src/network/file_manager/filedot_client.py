"""Filedot file manager client (web scraping).

Filedot runs XFileSharing Pro but has NOT enabled the API mod.
All operations go through the web panel using the session already
maintained by the upload worker's FileHostClient — this client
delegates all HTTP to that shared client so proxy, bandwidth
counter, session reuse, and reauth all happen through the same
pipeline as uploads.

Supported operations:
- List files and folders (scrape /files/?fld_id=N)
- Navigate into folders (via fld_id query param)
- Create folder (POST op=my_files, create_folder_submit)
- Delete file (GET /files?del_code=...&token=...)
- Delete folder (GET /files?fld_id=0&del_folder=...&token=...)
- Rename file (POST /file_edit?file_code=... with file_name)
- Rename folder (POST /fld_edit?fld_id=... with fld_name)
- Move files (POST op=my_files, to_folder_move)
- Copy files (POST op=my_files, to_folder_copy)
- Toggle public flag (POST set_flag=file_public)
- Toggle premium flag (POST set_flag=file_premium_only)
- Read file properties (GET /file_edit?file_code=...)
- Update file properties (POST /file_edit — single round-trip or
  multi-file diff-only)
- Get download link (https://filedot.to/<file_code>)
- Get account info (scrape /account/ used/total storage)

Two id types matter:
- file_code: alphanumeric, used in file URLs and as FileInfo.id
- file_id:   numeric, used by the action-panel form and set_flag AJAX.
  _scrape_page populates self._file_code_to_numeric as a per-folder
  cache so mutating ops can translate back.

The CSRF token is session-scoped: it is primed once by the first
list_files call and reused for every mutating op until a response
matches a stale-token marker, at which point it is cleared and the
next op re-primes.
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

FILEDOT_CAPABILITIES = FileManagerCapabilities(
    can_rename=True,
    can_move=True,
    can_delete=True,
    can_copy=True,
    can_change_access=False,  # Filedot uses independent flags, not tri-state
    can_edit_properties=True,
    can_set_file_flags=True,
    can_create_folder=True,
    can_remote_upload=False,
    can_trash=False,
    can_get_download_link=True,
    has_batch_operations=False,
    list_files_includes_folders=True,
    max_items_per_page=500,
    sortable_columns=["name"],
)

# File row: <tr class="filerow"> ... checkbox value="numeric" ... <a href=".../file_code">name</a> ... <td class="tdinfo">size</td>
_FILE_ROW_RE = re.compile(
    r'<tr class="filerow">'
    r'.*?name="file_id"\s+value="(\d+)"'
    r'.*?<td class="filename">\s*<a[^>]+href="https?://filedot\.(?:to|xyz)/([a-zA-Z0-9]+)"[^>]*>'
    r'\s*(.*?)\s*</a>'
    r'.*?<td class="tdinfo">\s*([^<]+?)\s*</td>',
    re.DOTALL,
)

# Folder row: <tr class="folderrow"> ... <a href=".../files?fld_id=N">name</a>
_FOLDER_ROW_RE = re.compile(
    r'<tr class="folderrow">'
    r'.*?href="https?://filedot\.(?:to|xyz)/files\?fld_id=(\d+)"[^>]*>'
    r'\s*(.*?)\s*</a>',
    re.DOTALL,
)

# CSRF token from any action link (delete/move use the same page token).
# The page encodes & as &amp; in attribute values, so don't anchor on [?&].
_TOKEN_RE = re.compile(r'token=([a-f0-9]{16,})', re.IGNORECASE)

# Hidden <input name="token" value="<hex>"> from the /file_edit or
# /fld_edit form. Separate from _TOKEN_RE which matches `token=<hex>` in
# URL query strings — this one matches the HTML attribute form.
_HIDDEN_TOKEN_INPUT_RE = re.compile(
    r'<input[^>]*\bname="token"[^>]*\bvalue="([a-f0-9]{16,})"',
    re.IGNORECASE,
)

# /file_edit form field parsers — XFS-standard layout, see
# tests/unit/network/file_manager/fixtures/filedot_file_edit.htm.
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
# Checkbox fields (file_public, file_premium_only) — detect the <input>
# row then check whether `checked` appears inside the same tag.
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

# Stale-token / session-expired markers (subset of filedot.json:42). A
# response body matching any of these means the cached action token has
# rotated and the caller should re-list to re-prime.
_STALE_TOKEN_MARKERS = (
    "Anti-CSRF check failed",
    "session expired",
    "token invalid",
    "invalid token",
)


def _is_stale_token_response(body: str) -> bool:
    """Return True if the response body indicates a rotated CSRF token."""
    low = body.lower()
    return any(marker.lower() in low for marker in _STALE_TOKEN_MARKERS)


def _parse_size(size_str: str) -> int:
    """Parse '2.4 GB' or '890 MB' to bytes."""
    size_str = size_str.strip().upper()
    for suffix, mult in sorted(_SIZE_MULTIPLIERS.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            try:
                return int(float(size_str[:-len(suffix)].strip()) * mult)
            except ValueError:
                return 0
    return 0


class FiledotFileManagerClient(FileManagerClient):
    """File manager for Filedot via web scraping.

    All HTTP is delegated to an injected FileHostClient so proxy,
    bandwidth tracking, session reuse, and reauth go through the same
    pipeline the upload worker already uses.
    """

    def __init__(self, file_host_client: FileHostClient, timeout: int = 30):
        """
        Args:
            file_host_client: The upload worker's FileHostClient for
                this host. All HTTP requests go through it, inheriting
                proxy, bandwidth counter, session cookies, and reauth.
            timeout: Per-request timeout in seconds.
        """
        self._http = file_host_client
        self.timeout = timeout
        # CSRF token scraped from the most recent list_files call.
        # Filedot's token is session-scoped, so this is primed once and
        # reused across every mutating operation until a stale-token error
        # forces a re-prime.
        self._action_token: str = ""
        # Maps alphanumeric file_code (used in URLs) to the numeric file_id
        # (used by the action-panel form and set_flag AJAX). Populated by
        # _scrape_page — cleared on every scrape so it stays consistent with
        # the currently displayed folder.
        self._file_code_to_numeric: Dict[str, str] = {}
        # Numeric folder ids seen in the most recent scrape. delete() uses
        # this to decide whether an id refers to a file or a folder.
        self._known_folder_ids: Set[str] = set()
        # Last folder_id value passed to list_files (as the caller sees it —
        # "/" for root or a numeric string for subfolders). Used by mutating
        # ops that need to implicitly re-prime the token + id caches.
        self._last_folder_id: str = ""
        # The fld_id form value for the current folder: "0" at root, the
        # numeric id otherwise. Sent as the `fld_id` POST field for move /
        # copy / create_folder / delete_bulk.
        self._last_list_fld_id: str = "0"

    # ------------------------------------------------------------------
    # Low-level web request — thin wrappers around FileHostClient.request
    # ------------------------------------------------------------------

    def _web_get(self, url: str) -> str:
        """GET request through the shared FileHostClient."""
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
        """POST form-urlencoded through the shared FileHostClient.

        Provide `fields` (dict, most callers) or `body` (pre-encoded bytes,
        used by move/copy which repeat `file_id=` for each selected item).
        """
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


    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    def _folder_url(self, folder_id: str, page: int = 1) -> str:
        """Build the file-listing URL for a given folder.

        Filedot's file manager lives at /files/. Root uses fld_id=0 per
        the action-panel select dropdown; subfolders use fld_id=<numeric>.
        """
        fld = folder_id if folder_id and folder_id not in ("/", "") else "0"
        return f"https://filedot.to/files/?fld_id={fld}&page={page}"

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def _scrape_page(self, folder_id: str, page: int) -> tuple[list, list]:
        """Fetch a folder page and return (folders, files) as FileInfo lists.

        Side effects:
        - Caches the CSRF token from the first action link found, which
          every mutating op needs.
        - Refreshes self._file_code_to_numeric and self._known_folder_ids so
          move/copy/delete/flag ops can resolve file_codes to numeric ids
          and distinguish files from folders.
        - Records self._last_folder_id and self._last_list_fld_id for
          implicit re-priming and for the fld_id POST field used by the
          action panel form.
        """
        html = self._web_get(self._folder_url(folder_id, page))

        # Cache CSRF token for this session — any action link has it
        token_match = _TOKEN_RE.search(html)
        if token_match:
            self._action_token = token_match.group(1)

        # Reset per-folder caches so a previous folder's ids do not leak
        # into the current view's mutating operations.
        self._file_code_to_numeric = {}
        self._known_folder_ids = set()
        self._last_folder_id = folder_id
        self._last_list_fld_id = (
            folder_id if folder_id and folder_id not in ("/", "") else "0"
        )

        folders = []
        for match in _FOLDER_ROW_RE.finditer(html):
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
        for match in _FILE_ROW_RE.finditer(html):
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

        log(f"Filedot scraped folder_id={folder_id!r} page={page}: "
            f"{len(folders)} folders, {len(files)} files "
            f"(token_cached={bool(self._action_token)}, "
            f"numeric_ids={len(self._file_code_to_numeric)})",
            level="debug", category="file_manager")

        return folders, files

    # ------------------------------------------------------------------
    # Cache + token helpers
    # ------------------------------------------------------------------

    def _ensure_token(self) -> None:
        """Prime _action_token and _file_code_to_numeric if empty.

        Called by every mutating op that needs either a token or a numeric
        id lookup. Primes against the last listed folder (or root if no
        list has happened yet).
        """
        if self._action_token and self._file_code_to_numeric is not None:
            return
        self._scrape_page(self._last_folder_id or "/", 1)

    def _resolve_numeric_ids(
        self, file_codes: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Map file_codes to their numeric file_id values.

        Re-primes the cache once (by re-scraping the current folder) if any
        code is missing, since a stale cache is the most common reason for
        a miss. Returns (resolved_numerics, still_missing_codes). The
        caller treats still-missing codes as failed items.
        """
        if not file_codes:
            return [], []

        numerics: List[str] = []
        missing: List[str] = []

        needs_reprime = any(
            code not in self._file_code_to_numeric for code in file_codes
        )
        if needs_reprime:
            try:
                self._scrape_page(self._last_folder_id or "/", 1)
            except Exception as e:
                log(f"Filedot: failed to re-prime numeric id cache: {e}",
                    level="warning", category="file_manager")

        for code in file_codes:
            num = self._file_code_to_numeric.get(code)
            if num:
                numerics.append(num)
            else:
                missing.append(code)

        return numerics, missing

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def list_files(
        self,
        folder_id: str = "/",
        page: int = 1,
        per_page: int = 50,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> FileListResult:
        folders, files = self._scrape_page(folder_id, page)

        # Return folders first, then files — the controller's file list
        # widget treats is_folder entries as navigable rows.
        items = folders + files
        return FileListResult(
            files=items,
            total=len(items),
            page=page,
            per_page=per_page,
        )

    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        """Return immediate child folders of parent_id for the tree widget."""
        folders, _files = self._scrape_page(parent_id, page=1)
        return FolderListResult(
            folders=folders, breadcrumb=[(parent_id, parent_id)]
        )

    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        """Create a folder via the main action-panel form.

        POSTs `op=my_files`, `token`, `fld_id=<parent>`, `create_new_folder=<name>`,
        `create_folder_submit=Create Folder` to https://filedot.to/.
        """
        self._ensure_token()
        if not self._action_token:
            return OperationResult(
                success=False,
                message="Could not prime action token for Filedot",
            )

        parent_fld = (
            parent_id if parent_id and parent_id not in ("/", "") else "0"
        )
        fields = {
            "op": "my_files",
            "token": self._action_token,
            "fld_id": parent_fld,
            "create_new_folder": name,
            "create_folder_submit": "Create Folder",
        }

        try:
            resp = self._web_post("https://filedot.to/", fields)
        except Exception as e:
            return OperationResult(success=False, message=str(e))

        if _is_stale_token_response(resp):
            # Token rotated — drop it so the next op re-primes.
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
        """Rename a file or folder via the edit forms.

        Dispatches to /fld_edit for folders (detected via _known_folder_ids)
        and /file_edit for files. Uses XFS-canonical field names: `fld_name`
        for folders, `file_name` for files.
        """
        self._ensure_token()
        if not self._action_token:
            return OperationResult(
                success=False,
                message="Could not prime action token for Filedot",
            )

        is_folder = item_id in self._known_folder_ids

        if is_folder:
            url = f"https://filedot.to/fld_edit?fld_id={item_id}"
            fields = {
                "op": "fld_edit",
                "fld_id": item_id,
                "fld_name": new_name,
                "token": self._action_token,
                "save": "Save",
            }
        else:
            url = f"https://filedot.to/file_edit?file_code={item_id}"
            fields = {
                "op": "file_edit",
                "file_code": item_id,
                "file_name": new_name,
                "token": self._action_token,
                "save": "Save",
            }

        try:
            resp = self._web_post(url, fields)
        except Exception as e:
            return OperationResult(success=False, message=str(e))

        if _is_stale_token_response(resp):
            self._action_token = ""
            return OperationResult(
                success=False,
                message="CSRF token rotated — refresh the folder and retry",
            )

        return OperationResult(success=True, message="Renamed")

    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        """Move files via the action-panel form (POST to_folder_move)."""
        return self._action_panel_bulk(
            item_ids, dest_folder_id, action_field="to_folder_move",
            action_value="Move files",
        )

    def delete(self, item_ids: List[str]) -> BatchResult:
        """Delete files and/or folders via the web panel.

        File delete:   GET /files?del_code=<code>&token=<tok>
        Folder delete: GET /files?fld_id=0&del_folder=<id>&token=<tok>
        Dispatch based on whether the id is in _known_folder_ids.
        """
        self._ensure_token()
        if not self._action_token:
            return BatchResult(
                succeeded=[],
                failed=[(i, "failed to prime action token") for i in item_ids],
            )

        succeeded: list = []
        failed: list = []

        for item_id in item_ids:
            try:
                if item_id in self._known_folder_ids:
                    url = (
                        "https://filedot.to/files?fld_id=0"
                        f"&del_folder={item_id}"
                        f"&token={self._action_token}"
                    )
                else:
                    url = (
                        f"https://filedot.to/files?del_code={item_id}"
                        f"&token={self._action_token}"
                    )
                resp = self._web_get(url)
                if _is_stale_token_response(resp):
                    self._action_token = ""
                    failed.append((item_id, "CSRF token rotated"))
                else:
                    succeeded.append(item_id)
            except Exception as e:
                failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def copy(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        """Copy files via the action-panel form (POST to_folder_copy)."""
        return self._action_panel_bulk(
            item_ids, dest_folder_id, action_field="to_folder_copy",
            action_value="Copy files",
        )

    def set_file_public(
        self, item_ids: List[str], value: bool
    ) -> BatchResult:
        """Toggle the file_public flag for selected files.

        Matches the AJAX call at logs/filedot.to-files.htm:10189-10210.
        POSTs to https://filedot.to/? with set_flag=file_public and a
        repeated file_id= for each numeric id.
        """
        return self._set_file_flag(item_ids, "file_public", value)

    def set_file_premium(
        self, item_ids: List[str], value: bool
    ) -> BatchResult:
        """Toggle the file_premium_only flag for selected files."""
        return self._set_file_flag(item_ids, "file_premium_only", value)

    def _set_file_flag(
        self, item_ids: List[str], flag_name: str, value: bool
    ) -> BatchResult:
        """Shared implementation for the two flag-toggle AJAX endpoints."""
        self._ensure_token()
        if not self._action_token:
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

        fields: list = [
            ("op", "my_files"),
            ("set_flag", flag_name),
            ("value", "1" if value else "0"),
            ("token", self._action_token),
        ]
        for num in numerics:
            fields.append(("file_id", num))

        body = urlencode(fields).encode("utf-8")

        try:
            resp = self._web_post("https://filedot.to/?", body=body)
        except Exception as e:
            return BatchResult(
                succeeded=[],
                failed=[(c, str(e)) for c in item_ids],
            )

        if _is_stale_token_response(resp):
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

    def _action_panel_bulk(
        self,
        item_ids: List[str],
        dest_folder_id: str,
        *,
        action_field: str,
        action_value: str,
    ) -> BatchResult:
        """Shared move/copy implementation.

        Posts the action-panel form with `file_id=<numeric>` repeated for
        each item plus `to_folder=<dest>` and the given action field/value.
        """
        self._ensure_token()
        if not self._action_token:
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

        fields: list = [
            ("op", "my_files"),
            ("token", self._action_token),
            ("fld_id", self._last_list_fld_id),
            ("to_folder", dest_fld),
            (action_field, action_value),
        ]
        for num in numerics:
            fields.append(("file_id", num))

        body = urlencode(fields).encode("utf-8")

        try:
            resp = self._web_post("https://filedot.to/", body=body)
        except Exception as e:
            return BatchResult(
                succeeded=[],
                failed=[(c, str(e)) for c in item_ids],
            )

        if _is_stale_token_response(resp):
            self._action_token = ""
            return BatchResult(
                succeeded=[],
                failed=[(c, "CSRF token rotated") for c in item_ids],
            )

        # Filedot returns the updated HTML page on success. Any input code
        # for which we had a numeric id is considered succeeded; anything we
        # could not resolve goes into failed.
        resolved_codes = [
            c for c in item_ids if c in self._file_code_to_numeric
        ]
        return BatchResult(
            succeeded=resolved_codes,
            failed=[(c, "no numeric id for file_code") for c in missing],
        )

    def read_file_properties(self, file_code: str) -> Dict[str, str]:
        """GET /file_edit?file_code=<code> and scrape the current field values.

        Returns a dict with keys file_name, file_descr, file_password,
        file_price, file_public, file_premium_only. Missing fields default
        to empty string / "0". Used by the single-file Properties dialog
        to pre-populate its widgets.
        """
        url = f"https://filedot.to/file_edit?file_code={file_code}"
        html = self._web_get(url)

        # Refresh the cached action token from the form's hidden input.
        # Defends against the (unlikely) case where Filedot starts issuing
        # per-form tokens — we pick up the fresh one here instead of
        # reusing a stale session token on the subsequent POST.
        token_match = _HIDDEN_TOKEN_INPUT_RE.search(html)
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
        """Apply a partial field update to one or many files.

        Single-file with round_trip=True: GET /file_edit to capture current
        values, merge in `fields`, POST the full form back. Preserves
        description / password / etc. that the user did not change.

        Multi-file or round_trip=False: skip the GETs. POST one form per
        file_code containing only the keys in `fields` (plus the mandatory
        op/file_code/token/save). Callers use this when they deliberately
        want the same diff applied to N files without reading each one.

        `file_name` is honored in single-file mode only — multi-file
        rename is nonsensical.
        """
        self._ensure_token()
        if not self._action_token:
            return BatchResult(
                succeeded=[],
                failed=[(c, "failed to prime action token") for c in file_codes],
            )

        succeeded: list = []
        failed: list = []

        single = len(file_codes) == 1 and round_trip

        for idx, code in enumerate(file_codes):
            url = f"https://filedot.to/file_edit?file_code={code}"
            try:
                if single:
                    current = self.read_file_properties(code)
                    merged = dict(current)
                    merged.update(fields)
                else:
                    merged = {
                        k: v for k, v in fields.items()
                        if k != "file_name"  # no multi-rename
                    }

                post_fields = {
                    "op": "file_edit",
                    "file_code": code,
                    "token": self._action_token,
                    "save": "Save",
                }
                post_fields.update(merged)

                resp = self._web_post(url, post_fields)
                if _is_stale_token_response(resp):
                    # Clear the token so the next op re-primes, mark this
                    # file failed, and abort the rest of the batch — the
                    # remaining files would all POST with an empty token
                    # and be silently rejected otherwise.
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
        # No file info endpoint — return minimal info from ID
        return [
            FileInfo(id=fid, name=fid, is_folder=False)
            for fid in item_ids
        ]

    def get_capabilities(self) -> FileManagerCapabilities:
        return FILEDOT_CAPABILITIES

    # ------------------------------------------------------------------
    # Optional operations
    # ------------------------------------------------------------------

    def get_download_link(self, file_id: str) -> str:
        return f"https://filedot.to/{file_id}"

    def get_account_info(self) -> dict:
        try:
            html = self._web_get("https://filedot.to/account/")
            storage_match = re.search(
                r'Used space:?\s*</td>\s*<td>\s*<(?:b|strong)>\s*([\d.]+)\s+of\s+([\d.]+)\s+GB',
                html, re.IGNORECASE,
            )
            if storage_match:
                used_gb = float(storage_match.group(1))
                total_gb = float(storage_match.group(2))
                return {
                    "storage_used": int(used_gb * 1024**3),
                    "storage_left": int((total_gb - used_gb) * 1024**3),
                }
        except Exception as e:
            log(f"Filedot account info failed: {e}",
                level="warning", category="file_manager")

        return {}
