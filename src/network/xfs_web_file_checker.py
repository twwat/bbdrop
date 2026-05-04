"""Account-walking link checker for XFS-web hosts (Filedot, Filespace).

Uses the existing XFSWebFileManagerBase scrape_page interface to walk
the user's folder tree, build a {file_code: FileInfo} inventory, and
match each gallery's file_codes against it. Mirrors the K2SFileChecker
shape so scan_coordinator can route both families with parallel logic.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from src.network.file_manager.client import FileInfo
from src.utils.logger import log


class XFSWebFileChecker:
    """File availability checker for XFS-web hosts.

    Wraps an XFSWebFileManagerBase instance (typically a
    FiledotFileManagerClient or FilespaceFileManagerClient).
    """

    def __init__(self, file_manager):
        self._fm = file_manager

    def walk_account(
        self, cancel_event: Optional[threading.Event] = None
    ) -> Dict[str, FileInfo]:
        """Walk root + non-empty subfolders; return {file_code: FileInfo}.

        Folders whose `file_count` metadata is 0 are skipped without an
        HTTP fetch. Folders whose file count exceeds PER_PAGE_MAX are
        paginated until a returned page has fewer rows than the limit.

        Returns:
            Dict keyed by file_code (the URL slug). Values are FileInfo
            with `size` and `is_available` populated by the host's
            scrape regex.
        """
        per_page = getattr(self._fm, "PER_PAGE_MAX", 500)
        inventory: Dict[str, FileInfo] = {}
        queue: List[str] = ["0"]  # root folder id
        # XFS panels render breadcrumb / parent back-links as folder rows,
        # so the same fld_id can show up in multiple parent listings.
        # Without this set the walker pingpongs and hammers the host.
        visited: set[str] = set()

        while queue:
            if cancel_event is not None and cancel_event.is_set():
                return {}
            folder_id = queue.pop()
            if folder_id in visited:
                continue
            visited.add(folder_id)
            page = 1
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    return {}
                try:
                    folders, files = self._fm._scrape_page(
                        folder_id, page, per_page=per_page
                    )
                except Exception as e:
                    log(
                        f"XFS scrape failed for folder={folder_id} page={page}: {e}",
                        level="error", category="scanner",
                    )
                    break

                for f in files:
                    inventory[f.id] = f

                if page == 1:
                    for fld in folders:
                        if fld.id in visited:
                            continue
                        # XFS panels include a ".." parent-nav row in
                        # subfolder listings; queueing it would re-enter
                        # the parent folder.
                        if fld.name == "..":
                            continue
                        count = fld.metadata.get("file_count")
                        if count is None or count > 0:
                            # Treat unknown counts as "fetch to be safe".
                            queue.append(fld.id)

                if len(files) < per_page:
                    break
                page += 1

        return inventory

    def check_gallery_from_inventory(
        self,
        file_code_to_url: Dict[str, str],
        inventory: Dict[str, FileInfo],
    ) -> Dict[str, Any]:
        """Match a gallery's file_codes against a pre-walked inventory.

        Returns dict with keys: status, online, offline, errors, total,
        offline_urls. status is 'online'/'offline'/'partial'/'unknown'.
        """
        if not file_code_to_url:
            return {
                "status": "unknown", "online": 0, "offline": 0,
                "errors": 0, "total": 0, "offline_urls": [],
            }

        online = 0
        offline = 0
        offline_urls: List[str] = []

        for code, url in file_code_to_url.items():
            info = inventory.get(code)
            if info is not None and info.is_available:
                online += 1
            else:
                offline += 1
                offline_urls.append(url)

        total = len(file_code_to_url)
        if offline == 0:
            status = "online"
        elif online == 0:
            status = "offline"
        else:
            status = "partial"

        return {
            "status": status,
            "online": online,
            "offline": offline,
            "errors": 0,
            "total": total,
            "offline_urls": offline_urls,
        }

    def calc_storage_used(self, inventory: Dict[str, FileInfo]) -> int:
        """Sum sizes of available files in the inventory."""
        return sum(
            info.size for info in inventory.values() if info.is_available
        )
