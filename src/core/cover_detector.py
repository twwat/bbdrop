"""Detect cover photo candidates from a list of filenames.

Uses configurable glob patterns (comma-separated).
First matching pattern wins, case-insensitive.

Additional functions detect covers by image dimensions, file size,
deduplication, and list-length limiting.
"""
from __future__ import annotations

import fnmatch
from typing import Dict, Optional, Sequence, Tuple


def _parse_patterns(patterns: str) -> list[str]:
    """Split comma-separated glob patterns, stripping whitespace."""
    if not patterns or not patterns.strip():
        return []
    return [p.strip() for p in patterns.split(",") if p.strip()]


def detect_cover(
    filenames: Sequence[str],
    patterns: str = "",
) -> Optional[str]:
    """Return the first filename matching any cover pattern, or None.

    Patterns are tried in order; within each pattern, files are tested
    in their original list order. First match wins.

    Args:
        filenames: Image filenames (basenames, not full paths).
        patterns: Comma-separated glob patterns, e.g. "cover*, poster*, *_cover.*"

    Returns:
        The matching filename, or None if no match.
    """
    pattern_list = _parse_patterns(patterns)
    if not pattern_list:
        return None

    for pattern in pattern_list:
        for fname in filenames:
            if fnmatch.fnmatch(fname.lower(), pattern.lower()):
                return fname

    return None


def detect_covers_by_filename(
    filenames: Sequence[str],
    patterns: str = "",
) -> list[str]:
    """Return ALL filenames matching any cover pattern (no duplicates).

    Unlike ``detect_cover`` which returns only the first match, this
    returns every matching filename while preserving list order and
    avoiding duplicates across patterns.

    Args:
        filenames: Image filenames (basenames, not full paths).
        patterns: Comma-separated glob patterns.

    Returns:
        List of matching filenames in their original order.
    """
    pattern_list = _parse_patterns(patterns)
    if not pattern_list:
        return []

    seen: set[str] = set()
    result: list[str] = []
    for fname in filenames:
        if fname in seen:
            continue
        for pattern in pattern_list:
            if fnmatch.fnmatch(fname.lower(), pattern.lower()):
                seen.add(fname)
                result.append(fname)
                break
    return result


def detect_cover_by_dimensions(
    file_dimensions: Dict[str, Tuple[int, int]],
    differs_percent: Optional[float] = None,
    min_shortest_side: Optional[int] = None,
    max_longest_side: Optional[int] = None,
) -> list[str]:
    """Detect covers by image dimensions.

    All specified criteria combine as AND -- a file must satisfy every
    active criterion to be included.

    Args:
        file_dimensions: Mapping of ``{filename: (width, height)}``.
        differs_percent: Include files whose pixel area differs from the
            average area by more than this percentage.
        min_shortest_side: Minimum size on the shortest side (inclusive).
            Rejects images where ``min(w, h) < min_shortest_side``.
        max_longest_side: Maximum size on the longest side (inclusive).
            Rejects images where ``max(w, h) > max_longest_side``.

    Returns:
        List of filenames matching all criteria, in iteration order.
    """
    if not file_dimensions:
        return []

    has_criteria = any(
        v is not None
        for v in (differs_percent, min_shortest_side, max_longest_side)
    )
    if not has_criteria:
        return []

    # Pre-compute average area for differs_percent check.
    avg_area: float = 0.0
    if differs_percent is not None:
        areas = [w * h for w, h in file_dimensions.values()]
        avg_area = sum(areas) / len(areas)

    result: list[str] = []
    for fname, (w, h) in file_dimensions.items():
        area = w * h

        if differs_percent is not None:
            if avg_area == 0:
                continue
            deviation = abs(area - avg_area) / avg_area * 100
            if deviation <= differs_percent:
                continue

        if min_shortest_side is not None and min(w, h) < min_shortest_side:
            continue
        if max_longest_side is not None and max(w, h) > max_longest_side:
            continue

        result.append(fname)

    return result


def detect_cover_by_file_size(
    file_sizes: Dict[str, int],
    min_kb: Optional[float] = None,
    max_kb: Optional[float] = None,
) -> list[str]:
    """Detect covers by file size in KB.

    Args:
        file_sizes: Mapping of ``{filename: size_in_bytes}``.
        min_kb: Minimum file size in KB (inclusive).
        max_kb: Maximum file size in KB (inclusive).

    Returns:
        List of filenames within the specified size range.
    """
    if min_kb is None and max_kb is None:
        return []

    result: list[str] = []
    for fname, size_bytes in file_sizes.items():
        size_kb = size_bytes / 1024

        if min_kb is not None and size_kb < min_kb:
            continue
        if max_kb is not None and size_kb > max_kb:
            continue

        result.append(fname)

    return result


def deduplicate_covers(
    candidates: Sequence[str],
    file_sizes: Dict[str, int],
) -> list[str]:
    """Remove duplicate cover candidates by file size.

    Files with the same byte size are considered likely copies.
    The first occurrence is kept.

    Args:
        candidates: Ordered list of candidate filenames.
        file_sizes: Mapping of ``{filename: size_in_bytes}``.

    Returns:
        De-duplicated list preserving original order.
    """
    seen_sizes: set[int] = set()
    result: list[str] = []
    for fname in candidates:
        size = file_sizes.get(fname)
        if size is None:
            # Unknown size -- keep it (cannot determine if duplicate).
            result.append(fname)
            continue
        if size not in seen_sizes:
            seen_sizes.add(size)
            result.append(fname)
    return result


def apply_max_covers(
    candidates: Sequence[str],
    max_covers: int,
) -> list[str]:
    """Limit the number of cover candidates.

    Args:
        candidates: Ordered list of candidate filenames.
        max_covers: Maximum number to keep. ``0`` means unlimited.

    Returns:
        Truncated (or full) list as a new list object.
    """
    if max_covers <= 0:
        return list(candidates)
    return list(candidates[:max_covers])
