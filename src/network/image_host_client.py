"""
Abstract base class for image host uploaders.

Thin interface that all image host implementations must follow.
Per-host subclasses handle the actual upload logic since flows differ
significantly between hosts (gallery creation, auth, thumbnails).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable

from src.core.image_host_config import ImageHostConfig


class ImageHostClient(ABC):
    """Abstract base for all image host uploaders."""

    def __init__(self, config: ImageHostConfig):
        self.config = config

    @property
    @abstractmethod
    def web_url(self) -> str:
        """Base web URL for this host (e.g. 'https://imx.to')."""
        ...

    @abstractmethod
    def upload_image(self, image_path: str, create_gallery: bool = False,
                     gallery_id: Optional[str] = None,
                     thumbnail_size: int = 3,
                     thumbnail_format: int = 2,
                     thread_session: Optional[Any] = None,
                     progress_callback: Optional[Callable] = None,
                     content_type: str = "all",
                     gallery_name: Optional[str] = None) -> Dict[str, Any]:
        """Upload single image. Return API response dict."""
        ...

    @staticmethod
    def normalize_response(status: str, image_url: str = '', thumb_url: str = '',
                           gallery_id: str | None = None, original_filename: str = '',
                           error: str | None = None, bbcode: str | None = None) -> dict:
        """Build a standard upload response dict.

        All ``upload_image`` implementations MUST return this shape so the
        engine and workers can consume responses without host-specific
        branching.
        """
        return {
            'status': status,
            'data': {
                'image_url': image_url,
                'thumb_url': thumb_url,
                'gallery_id': gallery_id,
                'original_filename': original_filename,
                'bbcode': bbcode,
            },
            'error': error,
        }

    def get_default_headers(self) -> dict:
        """Return default HTTP headers for this host.

        The engine calls this instead of accessing a ``.headers`` attribute
        directly, keeping the interface host-agnostic.
        """
        return {}

    def supports_gallery_rename(self) -> bool:
        """Whether this host supports renaming galleries after creation."""
        return False

    def sanitize_gallery_name(self, name: str) -> str:
        """Sanitize a gallery name for this host.

        Each host may have different rules for allowed characters.
        Default implementation strips control characters and trims whitespace.
        """
        import re
        sanitized = re.sub(r'[\x00-\x1f\x7f]', '', name)
        return sanitized.strip() or 'untitled'

    def get_gallery_url(self, gallery_id: str, gallery_name: str = "") -> str:
        """Get the gallery URL for a given gallery ID (and optional name)."""
        return self.config.gallery_url_template.format(gallery_id=gallery_id)

    def get_thumbnail_url(self, img_id: str, ext: str = "") -> str:
        """Get the thumbnail URL for a given image ID."""
        return self.config.thumbnail_url_template.format(img_id=img_id, ext=ext)
