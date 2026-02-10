"""Detect cover photo candidates from a list of filenames.

Uses configurable glob patterns (comma-separated).
First matching pattern wins, case-insensitive.
"""
from __future__ import annotations

import fnmatch
from typing import Optional, Sequence


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
    if not patterns or not patterns.strip():
        return None

    pattern_list = [p.strip() for p in patterns.split(",") if p.strip()]
    if not pattern_list:
        return None

    for pattern in pattern_list:
        for fname in filenames:
            if fnmatch.fnmatch(fname.lower(), pattern.lower()):
                return fname

    return None
