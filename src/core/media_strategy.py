"""Media strategy ABC for unified image/video pipeline."""
from abc import ABC, abstractmethod
from typing import Any


class MediaStrategy(ABC):
    """Abstract base for media type processing strategies.

    ImageStrategy handles image galleries (existing behavior).
    VideoStrategy handles video files (screenshot sheet + file host upload).
    """

    @abstractmethod
    def scan(self, path: str) -> dict:
        """Scan media files and return metadata dict."""

    @abstractmethod
    def prepare_upload(self, item: Any, settings: dict) -> dict:
        """Prepare upload context (client, content to upload, etc.)."""

    @abstractmethod
    def generate_primary_content(self, item: Any, settings: dict) -> dict:
        """Generate primary content for image host upload.

        For images: upload individual images, return per-image BBCode.
        For video: generate screenshot sheet, return single image.
        """

    @abstractmethod
    def get_template_placeholders(self, item: Any) -> dict:
        """Return dict of placeholder name -> value for template substitution.

        Video-specific placeholders return empty strings for ImageStrategy.
        """


class ImageStrategy(MediaStrategy):
    """Strategy for image gallery processing (existing behavior).

    Stub — will be wired to existing scan/upload/template logic.
    """

    def scan(self, path: str) -> dict:
        raise NotImplementedError("ImageStrategy.scan not yet wired")

    def prepare_upload(self, item: Any, settings: dict) -> dict:
        raise NotImplementedError("ImageStrategy.prepare_upload not yet wired")

    def generate_primary_content(self, item: Any, settings: dict) -> dict:
        raise NotImplementedError("ImageStrategy.generate_primary_content not yet wired")

    def get_template_placeholders(self, item: Any) -> dict:
        raise NotImplementedError("ImageStrategy.get_template_placeholders not yet wired")


class VideoStrategy(MediaStrategy):
    """Strategy for video file processing.

    Stub — will be implemented with VideoScanner + ScreenshotSheetGenerator.
    """

    def scan(self, path: str) -> dict:
        raise NotImplementedError("VideoStrategy.scan not yet wired")

    def prepare_upload(self, item: Any, settings: dict) -> dict:
        raise NotImplementedError("VideoStrategy.prepare_upload not yet wired")

    def generate_primary_content(self, item: Any, settings: dict) -> dict:
        raise NotImplementedError("VideoStrategy.generate_primary_content not yet wired")

    def get_template_placeholders(self, item: Any) -> dict:
        raise NotImplementedError("VideoStrategy.get_template_placeholders not yet wired")


def create_media_strategy(media_type: str) -> MediaStrategy:
    """Factory: return the right strategy for the given media type."""
    if media_type == "image":
        return ImageStrategy()
    elif media_type == "video":
        return VideoStrategy()
    else:
        raise ValueError(f"Unknown media type: {media_type!r}")
