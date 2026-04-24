"""
Artifact finder utility for locating gallery JSON and BBCode files by gallery ID.
"""
import os
import glob
from typing import Optional


def find_gallery_json_by_id(gallery_id: str, gallery_path: Optional[str] = None) -> Optional[str]:
    """
    Find JSON artifact file by gallery ID pattern (*_{gallery_id}.json).

    Args:
        gallery_id: The gallery ID to search for (e.g., "1gq6n")
        gallery_path: Optional path to check for .uploaded subfolder first

    Returns:
        Path to JSON file if found, None otherwise.
        Prefers .uploaded location if both exist.
    """
    if not gallery_id:
        return None

    search_locations = []

    # Check .uploaded subfolder first if gallery_path provided
    if gallery_path:
        base_dir = gallery_path if os.path.isdir(gallery_path) else os.path.dirname(gallery_path)
        uploaded_dir = os.path.join(base_dir, ".uploaded")
        if os.path.exists(uploaded_dir):
            search_locations.append(uploaded_dir)

    # Check central storage
    try:
        from src.utils.paths import get_central_storage_path
        central_path = get_central_storage_path()
        if os.path.exists(central_path):
            search_locations.append(central_path)
    except (ImportError, Exception):
        # Fallback to hardcoded path if imports fail
        home = os.path.expanduser("~")
        fallback_central = os.path.join(home, ".bbdrop", "galleries")
        if os.path.exists(fallback_central):
            search_locations.append(fallback_central)

    # Search for files matching the pattern
    # Escape gallery_id for glob — names with brackets like [1080p.HEVC]
    # would otherwise be interpreted as character classes
    escaped_id = glob.escape(gallery_id)
    for location in search_locations:
        pattern = os.path.join(location, f"*_{escaped_id}.json")
        matches = glob.glob(pattern)
        if matches:
            # Return the first match (most recent if multiple exist)
            return sorted(matches, key=os.path.getmtime, reverse=True)[0]

    return None


def find_gallery_bbcode(
    gallery_name: str,
    gallery_id: str,
    gallery_path: Optional[str] = None,
) -> Optional[str]:
    """
    Find BBCode artifact file by name and gallery ID.

    Searches in this order:
    1. .uploaded/ subfolder (if gallery_path provided)
    2. Central storage

    Args:
        gallery_name: Gallery name for filename construction
        gallery_id: Gallery ID for filename construction
        gallery_path: Optional path to gallery folder

    Returns:
        BBCode content if found, empty string otherwise.
    """
    from src.storage.gallery_management import build_gallery_filenames
    from src.utils.logger import log

    if not gallery_name or not gallery_id:
        return None

    _, _, bbcode_filename = build_gallery_filenames(gallery_name, gallery_id)
    log(
        f"artifact_finder: looking for {bbcode_filename} in .uploaded and central store",
        level="debug", category="fileio",
    )

    # Check .uploaded subfolder first
    if gallery_path:
        base_dir = gallery_path if os.path.isdir(gallery_path) else os.path.dirname(gallery_path)
        bbcode_path = os.path.join(base_dir, ".uploaded", bbcode_filename)
        log(
            f"artifact_finder: checking {bbcode_path}",
            level="debug", category="fileio",
        )
        if os.path.isfile(bbcode_path):
            try:
                with open(bbcode_path, encoding="utf-8") as f:
                    content = f.read()
                    log(
                        f"artifact_finder: found {bbcode_filename} in .uploaded ({len(content)} bytes)",
                        level="debug", category="fileio",
                    )
                    return content
            except OSError as e:
                log(
                    f"artifact_finder: error reading {bbcode_path}: {e}",
                    level="warning", category="fileio",
                )

    # Check central storage
    try:
        from src.utils.paths import get_central_storage_path
        central_path = get_central_storage_path()
        central_bbcode_path = os.path.join(central_path, bbcode_filename)
        log(
            f"artifact_finder: checking {central_bbcode_path}",
            level="debug", category="fileio",
        )
        if os.path.isfile(central_bbcode_path):
            with open(central_bbcode_path, encoding="utf-8") as f:
                content = f.read()
                log(
                    f"artifact_finder: found {bbcode_filename} in central ({len(content)} bytes)",
                    level="debug", category="fileio",
                )
                return content
    except Exception as e:
        log(
            f"artifact_finder: error checking central store: {e}",
            level="warning", category="fileio",
        )

    log(
        f"artifact_finder: {bbcode_filename} not found",
        level="debug", category="fileio",
    )
    return None