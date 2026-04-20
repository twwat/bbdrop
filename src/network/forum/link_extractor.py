"""Extract structured link map from a BBCode post body.

URL-only — no parsing of surrounding tags. Categorises by hostname against
known image/file hosts.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §1.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


IMAGE_HOST_DOMAINS = {
    "imx.to": "imx", "imx.cm": "imx",
    "turboimagehost.com": "turbo", "www.turboimagehost.com": "turbo",
    "pixhost.to": "pixhost", "img.pixhost.to": "pixhost", "t.pixhost.to": "pixhost",
}
FILE_HOST_DOMAINS = {
    "k2s.cc": "k2s", "keep2share.cc": "k2s", "keep2.cc": "k2s",
    "rapidgator.net": "rapidgator", "rapidgator.asia": "rapidgator",
    "katfile.com": "katfile",
    "filespace.com": "filespace",
    "filedot.xyz": "filedot", "filedot.to": "filedot",
}

_URL_RE = re.compile(r"https?://[^\s\[\]\"'<>()]+", re.IGNORECASE)


def extract_link_map(body: str) -> dict:
    """Return {image_hosts: [...], file_hosts: [...], others: [...]} where each
    entry is {url, host_kind?} (host_kind only for known categories)."""
    seen_image, seen_file, seen_other = set(), set(), set()
    out: dict = {"image_hosts": [], "file_hosts": [], "others": []}
    for url in _URL_RE.findall(body):
        url = url.rstrip(".,;:")
        host = urlparse(url).netloc.lower()
        if host in IMAGE_HOST_DOMAINS:
            if url in seen_image:
                continue
            seen_image.add(url)
            out["image_hosts"].append(
                {"url": url, "host_kind": IMAGE_HOST_DOMAINS[host]}
            )
        elif host in FILE_HOST_DOMAINS:
            if url in seen_file:
                continue
            seen_file.add(url)
            out["file_hosts"].append(
                {"url": url, "host_kind": FILE_HOST_DOMAINS[host]}
            )
        else:
            if url in seen_other:
                continue
            seen_other.add(url)
            out["others"].append({"url": url})
    return out
