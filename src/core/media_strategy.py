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

    Uses VideoScanner for metadata extraction and ScreenshotSheetGenerator
    for composite screenshot sheet creation.
    """

    def scan(self, path: str) -> dict:
        from src.processing.video_scanner import VideoScanner
        scanner = VideoScanner()
        return scanner.scan(path)

    def prepare_upload(self, item: Any, settings: dict) -> dict:
        raise NotImplementedError("VideoStrategy.prepare_upload not yet wired")

    def generate_primary_content(self, item: Any, settings: dict) -> dict:
        from src.processing.screenshot_sheet import ScreenshotSheetGenerator
        from src.processing.video_scanner import VideoScanner
        import tempfile
        from pathlib import Path

        scanner = VideoScanner()
        metadata = scanner.scan(item.path)
        if metadata is None:
            return {'status': 'error', 'error': 'Failed to scan video'}

        generator = ScreenshotSheetGenerator()
        header_template = settings.get('image_overlay_template', '')
        sheet = generator.generate(item.path, metadata, settings, header_template)
        if sheet is None:
            return {'status': 'error', 'error': 'Failed to generate screenshot sheet'}

        output_format = settings.get('output_format', 'PNG')
        suffix = '.png' if output_format == 'PNG' else '.jpg'
        temp_path = Path(tempfile.mkdtemp()) / f"{item.name}_sheet{suffix}"
        save_kwargs = {}
        if output_format == 'JPG':
            save_kwargs['quality'] = settings.get('jpg_quality', 85)
        sheet.save(str(temp_path), **save_kwargs)

        return {
            'status': 'success',
            'screenshot_sheet_path': str(temp_path),
            'metadata': metadata,
        }

    def get_template_placeholders(self, item: Any) -> dict:
        import os
        meta = getattr(item, 'video_metadata', {}) or {}
        video_streams = meta.get('video_streams', [])
        audio_streams = meta.get('audio_streams', [])

        placeholders = {
            'filename': os.path.basename(getattr(item, 'path', '')),
            'duration': self._format_duration(meta.get('duration', 0)),
            'resolution': f"{meta.get('width', '')}x{meta.get('height', '')}",
            'fps': str(meta.get('fps', '')),
            'bitrate': str(meta.get('bitrate', '')),
            'filesize': str(meta.get('filesize', '')),
            'video_codec': video_streams[0].get('format', '') if video_streams else '',
            'audio_codec': audio_streams[0].get('format', '') if audio_streams else '',
        }

        # Numbered audio track placeholders
        track_lines = []
        for i, track in enumerate(audio_streams):
            fmt = track.get('format', 'Unknown')
            ch = track.get('channels', '?')
            rate = track.get('sampling_rate', '?')
            br = track.get('bit_rate', '?')
            line = f"{fmt}: {ch}-CH {rate}Hz {br} bps"
            placeholders[f'audio_track_{i+1}'] = line
            track_lines.append(line)

        placeholders['audio_tracks'] = '\n'.join(track_lines)
        return placeholders

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration as H:MM:SS or MM:SS."""
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


def create_media_strategy(media_type: str) -> MediaStrategy:
    """Factory: return the right strategy for the given media type."""
    if media_type == "image":
        return ImageStrategy()
    elif media_type == "video":
        return VideoStrategy()
    else:
        raise ValueError(f"Unknown media type: {media_type!r}")
