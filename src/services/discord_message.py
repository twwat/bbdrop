"""Discord message text: per-event templates, rendering, escaping, splitting.

Templates use the BBCode template syntax (``#placeholder#`` and
``[if x]...[else]...[/if]``) but render Discord markdown. Text values
(gallery and host names, errors) are markdown-escaped so a name can never
format, forge a link or expand another placeholder; link values are built
here and inserted as-is.

Pure Python, no Qt: imported by NotificationManager and the settings tab.
"""

import os
import re
from typing import Dict, List

from src.core.host_registry import get_display_name
from src.services.discord_webhook import MAX_CONTENT
from src.utils.format_utils import format_binary_size
from src.utils.templates import _camel_to_snake, process_conditionals
from src.utils.template_utils import HostLinks, collect_file_host_links

PLACEHOLDER_NAMES = frozenset({
    'galleryName', 'pictureCount', 'folderSize', 'galleryLink', 'hostLinks',
    'failedHosts', 'hostName', 'hostLink', 'error', 'detail',
})

# Values for these keys are links built by format_host_links (or a raw URL)
# and are inserted without escaping.
LINK_FIELDS = frozenset({'host_links', 'host_link', 'gallery_link'})

# Shipped defaults contain no links: links reach Discord only when the user
# adds them. The [if] fallbacks keep them readable when a caller has no fields.
DEFAULT_MESSAGES: Dict[str, str] = {
    'queue_finished': '✅ BBDrop: all uploads complete',
    'gallery_completed': (
        '✅ Gallery uploaded[if galleryName]: #galleryName#[/if]'
        '[if failedHosts]\n⚠️ Failed on: #failedHosts#[/if]'
    ),
    'gallery_failed': (
        '❌ Gallery failed[if galleryName]: #galleryName#[/if]'
        '[if error] — #error#[/if]'
    ),
    'filehost_upload_completed': (
        '✅ [if hostName]#hostName#[else]File host[/if] upload complete'
        '[if galleryName]: #galleryName#[/if]'
    ),
    'filehost_upload_failed': (
        '❌ [if hostName]#hostName#[else]File host[/if] upload failed'
        '[if galleryName]: #galleryName#[/if][if error] — #error#[/if]'
    ),
    'filehost_spinup_complete': 'ℹ️ File host ready[if detail]: #detail#[/if]',
    'disk_space_warning': '⚠️ [if detail]#detail#[else]Disk space is running low[/if]',
}

LINK_PRESETS: Dict[str, str] = {
    'gallery_completed': (
        '✅ **#galleryName#** — #pictureCount# images, #folderSize#\n'
        '[if galleryLink]🖼️ [Gallery](#galleryLink#)[/if]\n'
        '[if hostLinks]📦 Downloads:\n'
        '#hostLinks#[/if]\n'
        '[if failedHosts]⚠️ Failed on: #failedHosts#[/if]'
    ),
    'filehost_upload_completed': '✅ #hostName#: #galleryName#\n#hostLink#',
}

_SAMPLE_HOST_LINKS = (
    '**Rapidgator**: [Part 1](https://rapidgator.net/file/abc) · '
    '[Part 2](https://rapidgator.net/file/def)\n'
    '[TezFiles](https://tezfiles.com/file/xyz)'
)

_GALLERY_NAME = ('#galleryName#', 'Gallery Name', 'Gallery name', 'Summer Set')
_GALLERY_LINK = ('#galleryLink#', 'Gallery Link', 'Image host gallery URL',
                 'https://imx.to/g/abc123')
_HOST_NAME = ('#hostName#', 'Host Name', 'File host display name', 'Rapidgator')
_ERROR = ('#error#', 'Error', 'Error message (paths and links removed)',
          'Connection timed out')

# (placeholder, button_label, tooltip, preview_value) — PlaceholderEditorDialog shape.
EVENT_PLACEHOLDERS: Dict[str, List[tuple]] = {
    'queue_finished': [
        ('#detail#', 'Detail', 'Extra detail, if any', ''),
    ],
    'gallery_completed': [
        _GALLERY_NAME,
        ('#pictureCount#', 'Picture Count', 'Number of images uploaded', '48'),
        ('#folderSize#', 'Folder Size', 'Total size of the gallery', '312.4 MiB'),
        _GALLERY_LINK,
        ('#hostLinks#', 'Host Links', 'Every completed file host link', _SAMPLE_HOST_LINKS),
        ('#failedHosts#', 'Failed Hosts', 'File hosts that failed (empty if none)', 'Keep2Share'),
    ],
    'gallery_failed': [_GALLERY_NAME, _ERROR],
    'filehost_upload_completed': [
        _GALLERY_NAME, _GALLERY_LINK, _HOST_NAME,
        ('#hostLink#', 'Host Link', "This host's link(s)",
         '[Rapidgator](https://rapidgator.net/file/abc)'),
    ],
    'filehost_upload_failed': [_GALLERY_NAME, _GALLERY_LINK, _HOST_NAME, _ERROR],
    'filehost_spinup_complete': [
        ('#detail#', 'Detail', 'Extra detail, if any', ''),
    ],
    'disk_space_warning': [
        ('#detail#', 'Detail', 'Disk space level', 'Disk space: warning'),
    ],
}

_ESCAPE_RE = re.compile(r'([\\*_~|>#\[\]()<:`])')
_PLACEHOLDER_RE = re.compile(
    '#(' + '|'.join(sorted(PLACEHOLDER_NAMES, key=len, reverse=True)) + ')#')
_LINK_SEP = ' · '
_BLANK = '\x00'   # marks blank lines the user wrote, so they survive rendering


def preview_fields(event_id: str) -> dict:
    """Sample field values for previewing an event's message."""
    return {
        _camel_to_snake(placeholder.strip('#')): preview
        for placeholder, _, _, preview in EVENT_PLACEHOLDERS.get(event_id, [])
    }


def escape_markdown(text: str) -> str:
    """Backslash-escape every character Discord markdown gives meaning to."""
    return _ESCAPE_RE.sub(r'\\\1', text)


def _link_url(url: str) -> str:
    return url.replace(' ', '%20').replace(')', '%29').replace('(', '%28')


def format_host_links(hosts: List[HostLinks]) -> str:
    """One line per host: ``[Host](url)``, or ``**Host**: [Part 1](url) · ...``."""
    lines = []
    for host in hosts:
        if not host.parts:
            continue
        name = escape_markdown(host.host_name)
        if len(host.parts) == 1:
            lines.append(f'[{name}]({_link_url(host.parts[0].url)})')
        else:
            links = _LINK_SEP.join(
                f'[Part {p.part_number + 1}]({_link_url(p.url)})' for p in host.parts)
            lines.append(f'**{name}**: {links}')
    return '\n'.join(lines)


def render(template: str, fields: dict) -> str:
    """Render a message template with the given snake_case fields."""
    # Protect blank lines the user wrote; any other line that ends up empty
    # was emptied by a false conditional and is dropped.
    marked = '\n'.join(line if line.strip() else _BLANK
                       for line in template.split('\n'))
    text = process_conditionals(marked, fields)
    text = '\n'.join('' if line == _BLANK else line
                     for line in text.split('\n') if line.strip())

    def substitute(match):
        key = _camel_to_snake(match.group(1))
        value = fields.get(key)
        value = '' if value is None else str(value)
        return value if key in LINK_FIELDS else escape_markdown(value)

    # One pass: a value is never scanned again for placeholders.
    return _PLACEHOLDER_RE.sub(substitute, text).strip()


def split_message(text: str, limit: int = MAX_CONTENT) -> List[str]:
    """Split text into chunks of at most ``limit`` chars, at line breaks.

    A line longer than ``limit`` is broken at its last `` · `` link
    separator before the limit, else at its last space (URLs never contain
    spaces); only a run without either is cut.
    """
    if not text.strip():
        return []
    pieces = []
    for line in text.split('\n'):
        while len(line) > limit:
            for sep in (_LINK_SEP, ' '):
                cut = line.rfind(sep, 0, limit + len(sep))
                if cut > 0:
                    pieces.append(line[:cut])
                    line = line[cut + len(sep):]
                    break
            else:
                pieces.append(line[:limit])
                line = line[limit:]
        pieces.append(line)

    chunks: List[str] = []
    current = None
    for piece in pieces:
        if current is None:
            current = piece
        elif len(current) + 1 + len(piece) <= limit:
            current = f'{current}\n{piece}'
        else:
            chunks.append(current)
            current = piece
    if current is not None:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def gallery_fields(item, rows: List[dict], queue_store, failed_host: str = '') -> dict:
    """Placeholder values for a finished gallery's message.

    ``rows`` are the gallery's file host rows; ``failed_host`` is a host whose
    failure has been signalled but may not be written to its row yet.
    """
    failed = []
    for row in rows:
        if row.get('status') == 'failed' and not row.get('deduped'):
            failed.append(row.get('host_name', ''))
    if failed_host:
        failed.append(failed_host)
    failed_names = []
    for host in failed:
        name = get_display_name(host) if host else ''
        if name and name not in failed_names:
            failed_names.append(name)

    return {
        'gallery_name': item.name or os.path.basename(item.path),
        'picture_count': str(item.uploaded_images or item.total_images),
        'folder_size': format_binary_size(item.total_size) if item.total_size else '',
        'gallery_link': item.gallery_url or '',
        'host_links': format_host_links(collect_file_host_links(queue_store, item.path)),
        'failed_hosts': ', '.join(failed_names),
    }


def filehost_fields(item, host_id: str, queue_store, gallery_path: str,
                    error: str = '') -> dict:
    """Placeholder values for one file host's completed or failed upload.

    ``item`` may be None (gallery no longer in the queue). The host's links
    are read only for a success.
    """
    host_link = ''
    if not error:
        host_link = format_host_links(
            collect_file_host_links(queue_store, gallery_path, host_id=host_id))
    return {
        'gallery_name': (item.name if item else '') or os.path.basename(gallery_path),
        'host_name': get_display_name(host_id),
        'gallery_link': (item.gallery_url if item else '') or '',
        'host_link': host_link,
        'error': error,
    }
