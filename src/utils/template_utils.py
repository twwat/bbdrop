"""Template utility functions for BBCode generation."""

import os
import re
import sqlite3
from collections import defaultdict
from src.storage.database import QueueStore
from src.utils.format_utils import format_binary_size
from src.utils.logger import log
from src.core.file_host_config import get_file_host_setting, get_config_manager


def _sub_token(text: str, token: str, value: str) -> str:
    """Replace a #token# placeholder, ignoring the case the user typed.

    The canonical spelling is camelCase (`#fileName#`), but host configs
    predating that convention use lowercase `#filename#`. Lowercase
    `#filename#` is also the video contact-sheet placeholder, which
    ``apply_template`` blanks for image galleries -- so a file host format
    using it would silently render empty. Consuming every casing here, ahead
    of ``apply_template``, makes both spellings work without rewriting the
    user's saved formats.

    The ``#`` delimiters anchor each match, so `#fileName#` cannot match
    inside `#fileBaseName#`. ``value`` is injected via a lambda so
    backslashes in filenames aren't interpreted as regex escapes.
    """
    return re.sub(
        r'#' + re.escape(token) + r'#',
        lambda _m: value,
        text,
        flags=re.IGNORECASE,
    )


def _minimal_url(host_id: str, url: str) -> str:
    """Return a shortened URL for hosts that have a known minimal form."""
    if host_id == 'rapidgator':
        m = re.match(r'https?://(?:rapidgator\.net|rg\.to)/file/([^/]+)', url)
        if m:
            return f"https://rg.to/file/{m.group(1)}"
    return url


def get_file_host_links_for_template(queue_store: QueueStore, gallery_path: str) -> str:
    """Get file host download URLs for BBCode template placeholder.

    Applies per-host BBCode formatting if configured, otherwise returns raw URLs.
    Supports multi-part archives: groups parts by host and labels them.

    Args:
        queue_store: Database instance
        gallery_path: Gallery folder path

    Returns:
        Newline-separated download URLs (formatted or raw), or empty string if none exist.
        Empty string (not "N/A") enables conditional template logic:
        [if hostLinks]Download: #hostLinks#[/if]

    Example (single part, with BBCode format "[url=#link#]#hostName#[/url]"):
        [url=https://rapidgator.net/file/abc123]Rapidgator[/url]
        [url=https://tezfiles.com/file/xyz789]TezFiles[/url]

    Example (multi-part, with BBCode format "[url=#link#]#hostName# - #partLabel#[/url]"):
        [url=https://rapidgator.net/file/abc]Rapidgator - Part 1[/url]
        [url=https://rapidgator.net/file/def]Rapidgator - Part 2[/url]
        [url=https://tezfiles.com/file/ghi]TezFiles - Part 1[/url]
        [url=https://tezfiles.com/file/jkl]TezFiles - Part 2[/url]
    """
    try:
        uploads = queue_store.get_file_host_uploads(gallery_path)

        config_manager = get_config_manager()

        from src.utils.paths import read_config
        _cfg = read_config()
        use_minimal_links = _cfg.get('Advanced', 'file_hosts/minimal_links', fallback='false').lower() == 'true'

        # Group completed uploads by host
        uploads_by_host = defaultdict(list)
        for u in uploads:
            if u['status'] != 'completed' or not u.get('download_url') or not u['download_url'].strip():
                continue
            uploads_by_host[u['host_name']].append(u)

        # Determine if any host has multiple parts
        has_multi_part = any(len(parts) > 1 for parts in uploads_by_host.values())

        # Count total parts across all hosts (for #partCount# placeholder)
        max((len(parts) for parts in uploads_by_host.values()), default=0)

        formatted_links = []
        for host_id, host_uploads in uploads_by_host.items():
            # Sort by part_number
            host_uploads.sort(key=lambda u: u.get('part_number', 0))

            bbcode_format = get_file_host_setting(host_id, 'bbcode_format', 'str')
            host_config = config_manager.hosts.get(host_id)
            host_name = host_config.name if host_config else host_id.capitalize()

            for u in host_uploads:
                download_url = u['download_url'].strip()
                if use_minimal_links:
                    download_url = _minimal_url(host_id, download_url)
                part_num = u.get('part_number', 0)

                if bbcode_format:
                    formatted = bbcode_format.replace('#link#', download_url)
                    formatted = formatted.replace('#hostName#', host_name)

                    # File size placeholder
                    file_size = u.get('file_size')
                    formatted = formatted.replace(
                        '#fileSize#',
                        format_binary_size(file_size) if file_size is not None else ''
                    )

                    # Filename placeholders. Strip the internal bbdrop_<id>_
                    # archive prefix — rows written before the worker started
                    # storing clean names still carry it in the DB.
                    from src.network.file_host_client import get_clean_filename
                    file_name_raw = u.get('file_name') or ''
                    file_name_basename = os.path.basename(file_name_raw) if file_name_raw else ''
                    file_name_basename = get_clean_filename(file_name_basename)
                    stem, ext_with_dot = os.path.splitext(file_name_basename)
                    file_ext = ext_with_dot[1:].lower() if ext_with_dot else ''
                    formatted = _sub_token(formatted, 'fileName', file_name_basename)
                    formatted = _sub_token(formatted, 'fileBaseName', stem)
                    formatted = _sub_token(formatted, 'fileExt', file_ext)

                    # Multi-part placeholders
                    if has_multi_part and len(host_uploads) > 1:
                        part_label = f"Part {part_num + 1}"
                        formatted = formatted.replace('#partLabel#', part_label)
                        formatted = formatted.replace('#partNumber#', str(part_num + 1))
                        formatted = formatted.replace('#partCount#', str(len(host_uploads)))
                    else:
                        # Single part — remove part placeholders cleanly
                        formatted = formatted.replace(' - #partLabel#', '')
                        formatted = formatted.replace('#partLabel#', '')
                        formatted = formatted.replace('#partNumber#', '1')
                        formatted = formatted.replace('#partCount#', '1')

                    formatted_links.append(formatted)
                else:
                    # No format - use raw URL
                    formatted_links.append(download_url)

        return "\n".join(formatted_links) if formatted_links else ""

    except (sqlite3.Error, OSError, KeyError) as e:
        log(f"Failed to retrieve file host links: {e}",
            level="warning", category="template")
        return ""
