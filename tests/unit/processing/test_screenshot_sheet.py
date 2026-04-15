"""Tests for ScreenshotSheetGenerator."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from PIL import Image
from src.processing.screenshot_sheet import ScreenshotSheetGenerator


def _make_varied_frame(height: int, width: int) -> np.ndarray:
    """Build a deterministic high-variance BGR frame so is_empty_frame()
    doesn't reject it as uniform."""
    frame = np.full((height, width, 3), 128, dtype=np.uint8)
    frame[: height // 4, :, :] = 255
    frame[height // 4 : height // 2, :, :] = 0
    return frame


class TestBlackFrameDetection:
    def test_black_frame_detected(self):
        gen = ScreenshotSheetGenerator()
        black = np.zeros((100, 100, 3), dtype=np.uint8)
        assert gen.is_empty_frame(black) is True

    def test_white_frame_detected(self):
        gen = ScreenshotSheetGenerator()
        white = np.full((100, 100, 3), 255, dtype=np.uint8)
        assert gen.is_empty_frame(white) is True

    def test_normal_frame_not_detected(self):
        gen = ScreenshotSheetGenerator()
        frame = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
        assert gen.is_empty_frame(frame) is False


class TestTimestampCalculation:
    def test_evenly_spaced_timestamps(self):
        gen = ScreenshotSheetGenerator()
        timestamps = gen.calculate_timestamps(duration=300.0, count=16)
        assert len(timestamps) == 16
        assert timestamps[0] > 0
        assert timestamps[-1] < 300.0
        gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        assert max(gaps) - min(gaps) < 1.0

    def test_single_timestamp(self):
        gen = ScreenshotSheetGenerator()
        timestamps = gen.calculate_timestamps(duration=100.0, count=1)
        assert len(timestamps) == 1
        assert timestamps[0] == 50.0


class TestTimestampFormatting:
    def test_basic_format(self):
        gen = ScreenshotSheetGenerator()
        assert gen._format_timestamp(3661.0) == "01:01:01"

    def test_with_ms(self):
        gen = ScreenshotSheetGenerator()
        assert gen._format_timestamp(61.5, show_ms=True) == "00:01:01.500"

    def test_with_frame_number(self):
        gen = ScreenshotSheetGenerator()
        result = gen._format_timestamp(10.0, frame_number=300, show_frame_number=True)
        assert result == "00:00:10 [F300]"


class TestSheetCompositing:
    def test_generates_image_with_correct_dimensions(self):
        gen = ScreenshotSheetGenerator()
        frames = []
        for i in range(4):
            img = Image.new('RGB', (320, 240), color=(100 + i*30, 50, 50))
            frames.append((img, float(i * 60)))

        settings = {
            'rows': 2,
            'cols': 2,
            'show_timestamps': True,
            'show_ms': False,
            'show_frame_number': False,
            'font_family': 'monospace',
            'font_color': '#ffffff',
            'bg_color': '#000000',
            'header_text': '',
        }

        sheet = gen.composite_sheet(frames, settings)
        assert isinstance(sheet, Image.Image)
        # 2 cols * 320 + 3 * 4 padding = 652
        assert sheet.width == 652
        # 2 rows * 240 + 3 * 4 padding = 492
        assert sheet.height == 492

    def test_empty_frames_returns_placeholder(self):
        gen = ScreenshotSheetGenerator()
        sheet = gen.composite_sheet([], {'bg_color': '#000000'})
        assert sheet.size == (640, 480)

    def test_header_adds_height(self):
        gen = ScreenshotSheetGenerator()
        frames = [(Image.new('RGB', (320, 240)), 0.0)]
        no_header = gen.composite_sheet(frames, {'rows': 1, 'cols': 1, 'header_text': ''})
        with_header = gen.composite_sheet(frames, {'rows': 1, 'cols': 1, 'header_text': 'Line1\nLine2'})
        assert with_header.height > no_header.height


def _make_frames(count=4, size=(320, 240)):
    """Create dummy frames for testing."""
    return [(Image.new('RGB', size, color='red'), float(i * 10)) for i in range(count)]


class TestCompositeSheetSettings:
    """Verify composite_sheet respects all settings from the dict."""

    def test_thumb_width_resizes_frames(self):
        gen = ScreenshotSheetGenerator()
        frames = _make_frames(4, size=(640, 480))
        settings = {
            'rows': 2, 'cols': 2,
            'thumb_width': 200,
            'show_timestamps': False,
        }
        sheet = gen.composite_sheet(frames, settings)
        assert sheet.width == 2 * 200 + 3 * 4

    def test_border_spacing(self):
        gen = ScreenshotSheetGenerator()
        frames = _make_frames(4, size=(100, 100))
        settings = {
            'rows': 2, 'cols': 2,
            'border_spacing': 20,
            'thumb_width': 100,
            'show_timestamps': False,
        }
        sheet = gen.composite_sheet(frames, settings)
        assert sheet.width == 260

    def test_default_padding_when_border_spacing_absent(self):
        gen = ScreenshotSheetGenerator()
        frames = _make_frames(4, size=(100, 100))
        settings = {
            'rows': 2, 'cols': 2,
            'thumb_width': 100,
            'show_timestamps': False,
        }
        sheet = gen.composite_sheet(frames, settings)
        assert sheet.width == 212

    def test_font_sizes_from_settings(self):
        gen = ScreenshotSheetGenerator()
        frames = _make_frames(1, size=(200, 150))
        settings = {
            'rows': 1, 'cols': 1,
            'thumb_width': 200,
            'header_font_size': 30,
            'ts_font_size': 20,
            'header_text': 'Test Header',
            'show_timestamps': True,
        }
        sheet = gen.composite_sheet(frames, settings)
        assert sheet is not None

    def test_font_family_from_settings(self):
        gen = ScreenshotSheetGenerator()
        frames = _make_frames(1, size=(200, 150))
        settings = {
            'rows': 1, 'cols': 1,
            'thumb_width': 200,
            'font_family': 'DejaVuSans',
            'show_timestamps': True,
        }
        sheet = gen.composite_sheet(frames, settings)
        assert sheet is not None


class TestExtractFramesResize:
    """extract_frames downscales decoded frames before holding them in
    memory, so peak memory is bounded by thumb_size, not source resolution."""

    @patch("src.processing.screenshot_sheet.cv2.VideoCapture")
    def test_resizes_when_thumb_size_set(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, _make_varied_frame(1080, 1920))
        cap.get.return_value = 5000.0  # 5s in ms
        mock_vc.return_value = cap

        gen = ScreenshotSheetGenerator()
        frames = gen.extract_frames(
            "/fake.mp4", [5.0], duration=10.0, thumb_size=(320, 180)
        )

        assert len(frames) == 1
        assert frames[0][0].size == (320, 180)

    @patch("src.processing.screenshot_sheet.cv2.VideoCapture")
    def test_keeps_source_size_when_no_thumb_size(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, _make_varied_frame(480, 640))
        cap.get.return_value = 5000.0
        mock_vc.return_value = cap

        gen = ScreenshotSheetGenerator()
        frames = gen.extract_frames("/fake.mp4", [5.0], duration=10.0)

        assert len(frames) == 1
        assert frames[0][0].size == (640, 480)
