"""
Artifact finder utility for locating gallery JSON and BBCode files by gallery ID.
"""
import os
import glob
from typing import Optional, Tuple


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


def resolve_gallery_json(
    gallery_path: str,
    gallery_name: str,
    gallery_id: str,
) -> Optional[str]:
    """Locate a gallery's JSON artifact and return its absolute path.

    Tries the canonical {name}_{id}.json first, then falls back to legacy
    duplicated/synth-id patterns. When a legacy file is found, it's renamed
    to the canonical filename (and its sibling _bbcode.txt is renamed
    alongside) so subsequent reads converge on a single naming convention.
    """
    if not gallery_path or not gallery_name or not gallery_id:
        return None
    from src.utils.logger import log

    base_dir = (
        gallery_path if os.path.isdir(gallery_path)
        else os.path.dirname(gallery_path)
    )
    uploaded_dir = os.path.join(base_dir, ".uploaded")
    try:
        from src.utils.paths import get_central_storage_path
        central_dir = get_central_storage_path()
    except Exception:
        central_dir = None

    canonical_name = f"{gallery_name}_{gallery_id}.json"

    def _candidates(directory: str) -> list:
        if not directory:
            return []
        out = [os.path.join(directory, canonical_name)]
        # Legacy: synthesized id == gallery_name (the duplicated case).
        out.append(os.path.join(directory, f"{gallery_name}_{gallery_name}.json"))
        stem = os.path.splitext(os.path.basename(gallery_path))[0]
        if stem and stem != gallery_name and stem != gallery_id:
            out.append(os.path.join(directory, f"{gallery_name}_{stem}.json"))
        return out

    for directory in (uploaded_dir, central_dir):
        if not directory or not os.path.isdir(directory):
            continue
        canonical_path = os.path.join(directory, canonical_name)
        for cand in _candidates(directory):
            if not os.path.isfile(cand):
                continue
            if os.path.normcase(cand) == os.path.normcase(canonical_path):
                return cand
            # Legacy hit — rename to canonical and rename its sibling .txt.
            try:
                if not os.path.exists(canonical_path):
                    os.rename(cand, canonical_path)
                    log(
                        f"resolve_gallery_json: renamed legacy "
                        f"{os.path.basename(cand)} -> {canonical_name}",
                        level="info", category="fileio",
                    )
                legacy_bbcode = cand[:-len(".json")] + "_bbcode.txt"
                canonical_bbcode = canonical_path[:-len(".json")] + "_bbcode.txt"
                if (
                    os.path.isfile(legacy_bbcode)
                    and not os.path.exists(canonical_bbcode)
                ):
                    os.rename(legacy_bbcode, canonical_bbcode)
                return canonical_path
            except OSError as e:
                log(
                    f"resolve_gallery_json rename failed ({cand}): {e}",
                    level="warning", category="fileio",
                )
                # Fall through to return whatever we found.
                return cand

    # Last resort: glob *_{gallery_id}.json in case name has shifted.
    for directory in (uploaded_dir, central_dir):
        if not directory or not os.path.isdir(directory):
            continue
        escaped = glob.escape(gallery_id)
        matches = glob.glob(os.path.join(directory, f"*_{escaped}.json"))
        if matches:
            return sorted(matches, key=os.path.getmtime, reverse=True)[0]

    return None


def _candidate_bbcode_paths(
    gallery_path: str, gallery_name: str, gallery_id: str
) -> list:
    """Return on-disk candidate paths to look for a gallery's BBCode .txt,
    in priority order. Includes the canonical post-v19 filename, the legacy
    duplicated "{name}_{name}" pattern from when the synthesized id equalled
    the gallery_name, and the older "{name}_{stem}" pattern from when the
    synthesized id was splitext(basename(path))[0].
    """
    base_dir = (
        gallery_path if os.path.isdir(gallery_path)
        else os.path.dirname(gallery_path)
    )
    uploaded_dir = os.path.join(base_dir, ".uploaded")
    try:
        from src.utils.paths import get_central_storage_path
        central_dir = get_central_storage_path()
    except Exception:
        central_dir = None

    candidates: list = []

    def _push(filename: str):
        if uploaded_dir:
            candidates.append(os.path.join(uploaded_dir, filename))
        if central_dir:
            candidates.append(os.path.join(central_dir, filename))

    if gallery_name and gallery_id:
        _push(f"{gallery_name}_{gallery_id}_bbcode.txt")
    if gallery_name:
        # Legacy: synthesized id == gallery_name (the duplicated case).
        _push(f"{gallery_name}_{gallery_name}_bbcode.txt")
    stem = os.path.splitext(os.path.basename(gallery_path))[0] if gallery_path else ""
    if gallery_name and stem and stem != gallery_name and stem != gallery_id:
        # Legacy: synthesized id == filename stem (different from name).
        _push(f"{gallery_name}_{stem}_bbcode.txt")
    return candidates


def _glob_bbcode_paths(gallery_id: str, gallery_path: str) -> list:
    """Last-resort glob: any *_{gallery_id}_bbcode.txt in .uploaded or central."""
    if not gallery_id:
        return []
    base_dir = (
        gallery_path if os.path.isdir(gallery_path)
        else os.path.dirname(gallery_path)
    ) if gallery_path else None
    search_dirs = []
    if base_dir:
        search_dirs.append(os.path.join(base_dir, ".uploaded"))
    try:
        from src.utils.paths import get_central_storage_path
        search_dirs.append(get_central_storage_path())
    except Exception:
        pass

    escaped = glob.escape(gallery_id)
    matches: list = []
    for d in search_dirs:
        if d and os.path.isdir(d):
            matches.extend(
                sorted(
                    glob.glob(os.path.join(d, f"*_{escaped}_bbcode.txt")),
                    key=os.path.getmtime, reverse=True,
                )
            )
    return matches


def resolve_gallery_bbcode(
    gallery_path: str,
    gallery_name: str = "",
    gallery_id: str = "",
) -> Tuple[str, Optional[str]]:
    """Resolve the BBCode for a gallery, DB-first with disk fallback.

    Returns (bbcode_text, source_description). Empty string if nothing found.

    Order of attempts:
      1. galleries.bbcode column (primary, post-v19)
      2. Canonical {name}_{id}_bbcode.txt on disk
      3. Legacy {name}_{name}_bbcode.txt (duplicated)
      4. Legacy {name}_{stem}_bbcode.txt
      5. Glob *_{id}_bbcode.txt as last resort

    On a successful disk fallback, the DB column is populated for next time
    AND a legacy duplicated/old filename is renamed to canonical so the
    on-disk artifacts converge to a single naming convention.
    """
    from src.utils.logger import log

    # Step 1 — DB column.
    if gallery_path:
        try:
            from src.storage.database import QueueStore
            store = QueueStore()
            text = store.get_gallery_bbcode(gallery_path)
            if text:
                return text, "database"
        except Exception as e:
            log(f"resolve_gallery_bbcode DB read failed: {e}",
                level="warning", category="fileio")

    # Resolve a gallery_id for disk fallback if caller didn't pass one.
    effective_id = gallery_id or ""
    if not effective_id and gallery_path:
        try:
            from src.storage.database import QueueStore
            effective_id = QueueStore().get_gallery_id(gallery_path)
        except Exception:
            effective_id = ""

    # Step 2-4 — known filename patterns.
    candidates = _candidate_bbcode_paths(
        gallery_path, gallery_name, effective_id
    )
    found_path: Optional[str] = None
    text = ""
    for cand in candidates:
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as f:
                    text = f.read()
                found_path = cand
                break
            except OSError as e:
                log(f"resolve_gallery_bbcode read failed at {cand}: {e}",
                    level="warning", category="fileio")

    # Step 5 — glob.
    if not text and effective_id:
        for cand in _glob_bbcode_paths(effective_id, gallery_path):
            try:
                with open(cand, encoding="utf-8") as f:
                    text = f.read()
                found_path = cand
                break
            except OSError:
                continue

    if not text:
        return "", None

    # Backfill the DB column so future reads skip the disk dance.
    if gallery_path:
        try:
            from src.storage.database import QueueStore
            QueueStore().set_gallery_bbcode(
                gallery_path, text,
                gallery_id=effective_id or None,
            )
        except Exception as e:
            log(f"resolve_gallery_bbcode DB backfill failed: {e}",
                level="warning", category="database")

    # Opportunistic rename: if we read from a legacy filename, rename it
    # (and its sibling .json) to the canonical {name}_{id}_*.* shape so
    # users see clean filenames going forward.
    if found_path and gallery_name and effective_id:
        canonical_bbcode = os.path.join(
            os.path.dirname(found_path),
            f"{gallery_name}_{effective_id}_bbcode.txt",
        )
        if os.path.normcase(found_path) != os.path.normcase(canonical_bbcode):
            try:
                if not os.path.exists(canonical_bbcode):
                    os.rename(found_path, canonical_bbcode)
                    log(
                        f"resolve_gallery_bbcode: renamed legacy "
                        f"{os.path.basename(found_path)} -> "
                        f"{os.path.basename(canonical_bbcode)}",
                        level="info", category="fileio",
                    )
                # Also rename the matching .json artifact if it followed the
                # same legacy convention.
                legacy_json = found_path[:-len("_bbcode.txt")] + ".json"
                canonical_json = canonical_bbcode[:-len("_bbcode.txt")] + ".json"
                if (
                    os.path.isfile(legacy_json)
                    and not os.path.exists(canonical_json)
                ):
                    os.rename(legacy_json, canonical_json)
            except OSError as e:
                log(
                    f"resolve_gallery_bbcode rename failed "
                    f"({found_path} -> canonical): {e}",
                    level="warning", category="fileio",
                )

    return text, found_path