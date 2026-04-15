"""Shared helpers for video screenshot sheet display.

Used by both the in-table hover preview (MediaTypeDelegate) and the
full ScreenshotSheetPreviewDialog so the on-disk convention only has
one source of truth.
"""
import hashlib
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

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


def get_cached_preview(sheet_path: str, target_width: int, cache_dir: str = "") -> str:
    """Return a path to a scaled preview PNG for tooltip use.

    Creates the cache dir on first use. Caches at
    ``<cache_dir>/<md5(sheet_path)>_<width>_<int(mtime)>.png`` — embedding
    the source mtime in the filename means any mtime change yields a fresh
    cache key, sidestepping same-second mtime races on coarse-resolution
    filesystems. Returns '' on failure (missing source, decode error,
    write error).

    Args:
        sheet_path: Absolute path to the source screenshot sheet.
        target_width: Desired width in px; height is scaled
            proportionally.
        cache_dir: Directory for cached scaled previews. When empty,
            defaults to ``<base>/sheets/.tooltips``.
    """
    if not sheet_path or not os.path.isfile(sheet_path):
        return ""

    if not cache_dir:
        cache_dir = os.path.join(get_base_path(), "sheets", ".tooltips")

    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError:
        return ""

    try:
        source_mtime = int(os.path.getmtime(sheet_path))
    except OSError:
        return ""

    key = hashlib.md5(sheet_path.encode()).hexdigest()
    cache_file = os.path.join(cache_dir, f"{key}_{target_width}_{source_mtime}.png")

    if os.path.isfile(cache_file):
        return cache_file

    image = QImage(sheet_path)
    if image.isNull():
        return ""

    scaled = image.scaledToWidth(
        target_width, Qt.TransformationMode.SmoothTransformation
    )
    if not scaled.save(cache_file, "PNG"):
        return ""
    return cache_file
