"""Shared helpers for video screenshot sheet display.

Used by both the in-table hover preview (MediaTypeDelegate) and the
full ScreenshotSheetPreviewDialog so the on-disk convention only has
one source of truth.
"""
import hashlib
import os

from src.utils.paths import get_base_path


def resolve_sheet_path(item) -> str:
    """Return the on-disk screenshot sheet path for a video item, or ''.

    Prefers ``item.screenshot_sheet_path`` when it points at a real file.
    Falls back to the md5-convention lookup in ``<base>/sheets/``, which
    is how sheets are located after a restart when the in-memory pointer
    has been lost.
    """
    in_memory = getattr(item, "screenshot_sheet_path", "") or ""
    if in_memory and os.path.isfile(in_memory):
        return in_memory

    item_path = getattr(item, "path", "") or ""
    if not item_path:
        return ""

    sheets_dir = os.path.join(get_base_path(), "sheets")
    path_hash = hashlib.md5(item_path.encode()).hexdigest()[:12]
    for ext in (".png", ".jpg"):
        candidate = os.path.join(sheets_dir, f"{path_hash}{ext}")
        if os.path.isfile(candidate):
            return candidate
    return ""
