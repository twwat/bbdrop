"""Tests for ScreenshotSheetGenerator."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from PIL import Image
from src.processing.screenshot_sheet import ScreenshotSheetGenerator


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
