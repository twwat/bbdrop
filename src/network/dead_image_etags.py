"""Dead-image ETag catalog and HEAD-request helper for thumbnail checking.

Image hosts return HTTP 200 with a placeholder image when content is removed.
The only reliable detection method is matching the response ETag against known
placeholder ETags. This catalog is sourced from production observation.
"""

from typing import Optional, Dict, Any

import requests

from src.utils.logger import log


DEAD_IMAGE_ETAGS: frozenset[str] = frozenset({
    '"65c43e4c-23a8"', '"65c43e4c-23a9"', '"573c4704-a0c4"',
    '"5c0710b7-44e3"', '"5c0710b7-44e2"', '"5a5e2c58-4a97"',
    '"5a5e2c58-4a96"', '"661caf88-5277"', '"55c78bab-4a96"',
    '"55c78bab-4a97"', '"573c4704-a0c5"', '"65a72a8c-1a47"',
    '"659a6c09-1a47"', '"6421c28f-1a47"', '"5ba88d20-4a96"',
    '"5ba88d20-4a97"', '"5d0a7dde-6ad0"', '"5d0a7dde-6ad1"',
    '"5c22be10-5277"', '"5adb7bc4-bb3c"', '"5adb7bc4-bb3d"',
    '"661c5638-5277"', '"5df9be54-9b5f"', '"5df9be54-9b60"',
    '"5cf6b5e8-4a96"', '"5cf6b5e8-4a97"', '"6040e00c-6ad0"',
    '"6040e00c-6ad1"', '"66c39e36-d70"', '"66c39e36-d71"',
    '"66a54c56-48a"', '"5c0710b7-4e9f"', '"5c0710b7-4ea0"',
    '"5d0a7dde-7066"', '"5d0a7dde-7067"', '"64ac6600-1e26"',
    '"64ac6600-1e27"', '"6421c28f-1a48"', '"5a5e2c58-3ed0"',
    '"5a5e2c58-3ed1"', '"5c0710b7-3dfe"', '"5c0710b7-3dff"',
    '"5e55cf9a-6ad0"', '"5e55cf9a-6ad1"', '"5ed2621c-4a96"',
    '"5ed2621c-4a97"', '"65c43e4c-1a47"', '"65c43e4c-1a48"',
    '"573c4704-a085"', '"573c4704-a086"', '"65a72a8c-1a48"',
    '"59d02738-4a96"', '"59d02738-4a97"', '"659a6c09-1a48"',
    '"55c78bab-3ed0"', '"55c78bab-3ed1"', '"6421c28f-1e26"',
    '"5ba88d20-3ed0"', '"5ba88d20-3ed1"', '"6421c28f-1e27"',
    '"5c22be10-4a96"', '"5c22be10-4a97"', '"5adb7bc4-ad09"',
    '"5adb7bc4-ad0a"', '"5df9be54-8d2d"', '"5df9be54-8d2e"',
    '"5cf6b5e8-3ed0"', '"5cf6b5e8-3ed1"', '"6040e00c-5c9e"',
    '"6040e00c-5c9f"', '"66c39e36-b06"', '"66c39e36-b07"',
    '"5d0a7dde-5c9d"', '"5d0a7dde-5c9e"', '"64ac6600-1a47"',
    '"64ac6600-1a48"', '"5e55cf9a-5c9e"', '"5e55cf9a-5c9f"',
    '"5ed2621c-3ed0"', '"5ed2621c-3ed1"', '"59d02738-3ed0"',
    '"59d02738-3ed1"',
})

# Early-exit: if the first N thumbnails are all dead, assume entire gallery is dead.
EARLY_EXIT_THRESHOLD = 25


def is_dead_image_etag(etag: Optional[str]) -> bool:
    """Check if an ETag matches a known dead-image placeholder.

    Args:
        etag: ETag header value from HEAD response, or None.

    Returns:
        True if the ETag matches a known placeholder image.
    """
    if not etag:
        return False
    return etag in DEAD_IMAGE_ETAGS


def check_thumbnail_head(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Perform a HEAD request on a thumbnail URL and check liveness.

    Returns a dict with:
    - 'url': the checked URL
    - 'status': 'online' | 'offline' | 'error'
    - 'etag': the ETag header value (if present)
    - 'error': error message (only if status == 'error')

    Args:
        url: Thumbnail URL to check.
        timeout: Request timeout in seconds.
    """
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        etag = resp.headers.get('ETag')

        if resp.status_code == 404:
            return {'url': url, 'status': 'offline', 'etag': etag}

        if resp.status_code == 200:
            if is_dead_image_etag(etag):
                return {'url': url, 'status': 'offline', 'etag': etag}
            return {'url': url, 'status': 'online', 'etag': etag}

        # Other status codes (403, 500, etc.) — treat as error
        return {'url': url, 'status': 'error', 'error': f'HTTP {resp.status_code}'}

    except requests.Timeout as e:
        return {'url': url, 'status': 'error', 'error': str(e)}
    except requests.ConnectionError as e:
        return {'url': url, 'status': 'error', 'error': str(e)}
    except requests.RequestException as e:
        return {'url': url, 'status': 'error', 'error': str(e)}
