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
                     progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Upload single image. Return API response dict."""
        ...

    def get_gallery_url(self, gallery_id: str) -> str:
        """Get the gallery URL for a given gallery ID."""
        return self.config.gallery_url_template.format(gallery_id=gallery_id)

    def get_thumbnail_url(self, img_id: str, ext: str = "") -> str:
        """Get the thumbnail URL for a given image ID."""
        return self.config.thumbnail_url_template.format(img_id=img_id, ext=ext)
