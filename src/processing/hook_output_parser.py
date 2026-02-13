"""
Parse hook stdout for URLs, file paths, and key-value pairs.

Uses region-claiming to prevent overlapping matches:
1. URLs matched first, their spans are claimed
2. Paths matched next, skipping regions inside URLs
3. Key-value pairs matched last, skipping regions inside URLs or paths
"""
import re
from typing import List, Dict, Any
from urllib.parse import urlparse
from pathlib import PurePosixPath, PureWindowsPath


def detect_stdout_values(text: str) -> List[Dict[str, Any]]:
    """
    Detect URLs, file paths, and key-value pairs in plain text.

    Returns a list of dicts, each with:
        - type: 'url' | 'path' | 'data'
        - value: the matched string
        - index: positional index within its type (1-based)
        - key: for 'data' type, the key name; None for url/path
        - span: (start, end) character positions in the original text
    """
    results = []
    claimed_spans = []

    # Phase 1: URLs (highest priority)
    url_pattern = re.compile(r'(?:https?|ftp)://[^\s<>"\'\)]+')
    for match in url_pattern.finditer(text):
        claimed_spans.append(match.span())
        results.append({
            'type': 'url',
            'value': match.group().rstrip('.,;:'),
            'key': None,
            'span': match.span(),
        })

    # Phase 2: File paths (skip regions inside URLs)
    # Windows paths: C:\... (drive letter + backslash)
    win_path_pattern = re.compile(
        r'[A-Za-z]:\\(?:[^\\\/:*?"<>|\r\n]+\\)*[^\\\/:*?"<>|\r\n]*'
    )
    # Unix paths: /... (not preceded by another /)
    unix_path_pattern = re.compile(r'(?<!/)/(?:[^\s:*?"<>|\r\n]+)')

    for pattern in [win_path_pattern, unix_path_pattern]:
        for match in pattern.finditer(text):
            if _overlaps_claimed(match.span(), claimed_spans):
                continue
            value = match.group()
            # Only keep paths that look like actual files (have extension)
            # or are clearly directory paths (end with / or \)
            last_part = value.replace('\\', '/').split('/')[-1]
            if '.' not in last_part and not value.endswith(('/', '\\')):
                continue
            claimed_spans.append(match.span())
            results.append({
                'type': 'path',
                'value': value,
                'key': None,
                'span': match.span(),
            })

    # Phase 3: Key-value pairs (skip regions inside URLs or paths)
    kv_pattern = re.compile(r'(\w+)\s*[:=]\s*([^\s,;\n]+)')
    for match in kv_pattern.finditer(text):
        if _overlaps_claimed(match.span(), claimed_spans):
            continue
        key = match.group(1)
        value = match.group(2)
        # Reject single-char keys before :\ (drive letters)
        if len(key) == 1 and value.startswith('\\'):
            continue
        claimed_spans.append(match.span())
        results.append({
            'type': 'data',
            'value': value,
            'key': key,
            'span': match.span(),
        })

    # Assign positional indices per type
    type_counters = {}
    for item in results:
        t = item['type']
        type_counters[t] = type_counters.get(t, 0) + 1
        item['index'] = type_counters[t]

    return results


def resolve_placeholder(placeholder: str, detected: List[Dict[str, Any]]) -> str:
    """
    Resolve a positional placeholder like URL[1], PATH[-1], URL[2].filename
    against a list of detected values.

    For JSON key names (no brackets), returns empty string (handled separately).

    Returns the resolved value, or empty string if not found.
    """
    match = re.match(
        r'^(URL|PATH)\[(-?\d+)\](?:\.(\w+))?$', placeholder, re.IGNORECASE
    )
    if not match:
        return ''

    type_name = match.group(1).lower()
    index = int(match.group(2))
    component = match.group(3)

    # Filter to matching type
    typed = [v for v in detected if v['type'] == type_name]
    if not typed:
        return ''

    # Resolve index (1-based positive, negative from end)
    try:
        if index > 0:
            item = typed[index - 1]
        elif index < 0:
            item = typed[index]
        else:
            return ''
    except IndexError:
        return ''

    value = item['value']

    if not component:
        return value

    return extract_component(value, type_name, component)


def extract_component(value: str, value_type: str, component: str) -> str:
    """Extract a sub-component from a URL or path value."""
    # .ext is shorthand for .extension
    if component == 'ext':
        component = 'extension'

    if value_type == 'url':
        parsed = urlparse(value)
        path_obj = PurePosixPath(parsed.path)
        components = {
            'domain': parsed.hostname or '',
            'filename': path_obj.name,
            'path': parsed.path,
            'extension': path_obj.suffix,
            'stem': path_obj.stem,
        }
    elif value_type == 'path':
        if '\\' in value or (len(value) >= 2 and value[1] == ':'):
            path_obj = PureWindowsPath(value)
        else:
            path_obj = PurePosixPath(value)
        components = {
            'filename': path_obj.name,
            'dir': str(path_obj.parent),
            'extension': path_obj.suffix,
            'stem': path_obj.stem,
        }
    else:
        return ''

    return components.get(component, '')


def _overlaps_claimed(span, claimed_spans):
    """Check if a span overlaps with any claimed span."""
    start, end = span
    for cs, ce in claimed_spans:
        if start < ce and end > cs:
            return True
    return False


def get_available_components(value_type: str) -> List[Dict[str, str]]:
    """
    Return the sub-components available for a given value type.
    Used by the mapper dialog to show expandable options.
    """
    if value_type == 'url':
        return [
            {'key': 'domain', 'label': '.domain'},
            {'key': 'filename', 'label': '.filename'},
            {'key': 'path', 'label': '.path'},
            {'key': 'extension', 'label': '.extension'},
            {'key': 'stem', 'label': '.stem'},
        ]
    elif value_type == 'path':
        return [
            {'key': 'filename', 'label': '.filename'},
            {'key': 'dir', 'label': '.dir'},
            {'key': 'extension', 'label': '.extension'},
            {'key': 'stem', 'label': '.stem'},
        ]
    return []
