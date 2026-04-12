"""Screenshot sheet generation for video files."""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import List, Optional, Tuple

from src.utils.logger import log


class ScreenshotSheetGenerator:
    """Generates a composite screenshot sheet from video frames."""

    VARIANCE_THRESHOLD = 15.0
    MAX_FRAME_RETRIES = 5
    RETRY_ADVANCE_SECONDS = 2.0

    def is_empty_frame(self, frame: np.ndarray) -> bool:
        """Detect black, white, or near-uniform frames."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        variance = float(np.var(gray))
        return variance < self.VARIANCE_THRESHOLD

    def calculate_timestamps(self, duration: float, count: int) -> List[float]:
        """Calculate evenly-spaced timestamps, avoiding very start/end."""
        margin = duration * 0.02
        usable = duration - 2 * margin
        if count <= 1:
            return [duration / 2]
        step = usable / (count - 1)
        return [margin + i * step for i in range(count)]

    def _try_extract_frame(
        self, cap: cv2.VideoCapture, timestamp: float, duration: float = 0
    ) -> Optional[Tuple[np.ndarray, float]]:
        """Try to extract a non-empty frame at or near the timestamp."""
        for attempt in range(self.MAX_FRAME_RETRIES):
            seek_time = timestamp + attempt * self.RETRY_ADVANCE_SECONDS
            if duration > 0 and seek_time >= duration:
                break
            cap.set(cv2.CAP_PROP_POS_MSEC, seek_time * 1000)
            ret, frame = cap.read()
            if not ret:
                return None
            if not self.is_empty_frame(frame):
                actual_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                return (frame, actual_time)
        # All retries were empty — return last frame anyway
        return (frame, seek_time) if ret else None

    def extract_frames(
        self, video_path: str, timestamps: List[float], duration: float = 0
    ) -> List[Tuple[Image.Image, float]]:
        """Extract frames at given timestamps, skipping black frames."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            log(f"ScreenshotSheet: cannot open {video_path}")
            return []

        frames = []
        try:
            for ts in timestamps:
                result = self._try_extract_frame(cap, ts, duration=duration)
                if result is not None:
                    bgr_frame, actual_ts = result
                    rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
                    pil_image = Image.fromarray(rgb_frame)
                    frames.append((pil_image, actual_ts))
        finally:
            cap.release()

        return frames

    def _format_timestamp(
        self, seconds: float, show_ms: bool = False, frame_number: int = None,
        show_frame_number: bool = False
    ) -> str:
        """Format seconds as HH:MM:SS with optional ms/frame."""
        seconds = max(0.0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        text = f"{h:02d}:{m:02d}:{s:02d}"
        if show_ms:
            ms = int((seconds % 1) * 1000)
            text += f".{ms:03d}"
        if show_frame_number and frame_number is not None:
            text += f" [F{frame_number}]"
        return text

    def _get_font(self, font_family: str, size: int) -> ImageFont.FreeTypeFont:
        """Load a font, falling back to default monospace."""
        try:
            return ImageFont.truetype(font_family, size)
        except (OSError, IOError):
            for fallback in ["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf",
                             "Consolas", "Courier New", "monospace"]:
                try:
                    return ImageFont.truetype(fallback, size)
                except (OSError, IOError):
                    continue
            return ImageFont.load_default()

    def composite_sheet(
        self,
        frames: List[Tuple[Image.Image, float]],
        settings: dict,
    ) -> Image.Image:
        """Composite frames into a grid with header and timestamps."""
        rows = settings.get('rows', 4)
        cols = settings.get('cols', 4)
        show_ts = settings.get('show_timestamps', True)
        show_ms = settings.get('show_ms', False)
        show_frame = settings.get('show_frame_number', False)
        font_family = settings.get('font_family', 'monospace')
        font_color = settings.get('font_color', '#ffffff')
        bg_color = settings.get('bg_color', '#000000')
        header_text = settings.get('header_text', '')
        padding = settings.get('border_spacing', 4)
        header_font_size = settings.get('header_font_size', 14)
        ts_font_size = settings.get('ts_font_size', 12)
        thumb_width = settings.get('thumb_width', 0)
    fps = settings.get('fps', 0)

        if not frames:
            return Image.new('RGB', (640, 480), color=bg_color)

        # Resize frames to target thumbnail width if set
        source_w, source_h = frames[0][0].size
        if thumb_width > 0 and thumb_width != source_w:
            aspect = source_h / source_w
            thumb_h = int(thumb_width * aspect)
            frames = [(f.resize((thumb_width, thumb_h), Image.LANCZOS), ts) for f, ts in frames]
            source_w, source_h = thumb_width, thumb_h

        thumb_w, thumb_h = source_w, source_h

        header_font = self._get_font(font_family, header_font_size)
        ts_font = self._get_font(font_family, ts_font_size)

        header_height = 0
        if header_text:
            header_lines = header_text.strip().split('\n')
            header_height = len(header_lines) * (header_font_size + 4) + padding * 2

        grid_w = cols * thumb_w + (cols + 1) * padding
        grid_h = rows * thumb_h + (rows + 1) * padding
        total_w = grid_w
        total_h = header_height + grid_h

        sheet = Image.new('RGB', (total_w, total_h), color=bg_color)
        draw = ImageDraw.Draw(sheet)

        if header_text:
            y = padding
            for line in header_lines:
                draw.text((padding, y), line, fill=font_color, font=header_font)
                y += header_font_size + 4

        for idx, (frame, ts) in enumerate(frames):
            if idx >= rows * cols:
                break
            row = idx // cols
            col = idx % cols
            x = padding + col * (thumb_w + padding)
            y = header_height + padding + row * (thumb_h + padding)

            if frame.size != (thumb_w, thumb_h):
                frame = frame.resize((thumb_w, thumb_h), Image.LANCZOS)
            sheet.paste(frame, (x, y))

            if show_ts:
                video_frame_num = int(ts * fps) if fps > 0 else idx
                ts_text = self._format_timestamp(ts, show_ms=show_ms, frame_number=video_frame_num, show_frame_number=show_frame)
                tx = x + 4
                ty = y + thumb_h - ts_font_size - 8
                draw.text((tx + 1, ty + 1), ts_text, fill='#000000', font=ts_font)
                draw.text((tx, ty), ts_text, fill=font_color, font=ts_font)

        return sheet

    def generate(
        self,
        video_path: str,
        metadata: dict,
        settings: dict,
        header_template: str = '',
    ) -> Optional[Image.Image]:
        """Full pipeline: calculate timestamps, extract frames, composite."""
        rows = settings.get('rows', 4)
        cols = settings.get('cols', 4)
        count = rows * cols
        duration = metadata.get('duration', 0)

        if duration <= 0:
            log(f"ScreenshotSheet: invalid duration for {video_path}")
            return None

        timestamps = self.calculate_timestamps(duration, count)
        frames = self.extract_frames(video_path, timestamps, duration=duration)

        if not frames:
            log(f"ScreenshotSheet: no frames extracted from {video_path}")
            return None

        header_text = header_template
        for key, value in metadata.items():
            if isinstance(value, (str, int, float)):
                header_text = header_text.replace(f'#{key}#', str(value))

        settings_with_header = {**settings, 'header_text': header_text, 'fps': metadata.get('fps', 0)}
        return self.composite_sheet(frames, settings_with_header)
