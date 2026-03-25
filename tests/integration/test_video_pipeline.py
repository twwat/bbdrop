"""End-to-end smoke test for video pipeline."""
import pytest
import tempfile
import os
import numpy as np
import cv2
from pathlib import Path
from src.processing.video_scanner import VideoScanner
from src.processing.screenshot_sheet import ScreenshotSheetGenerator


@pytest.mark.integration
class TestVideoPipelineSmoke:
    @pytest.fixture
    def test_video(self, tmp_path):
        """Generate a small synthetic test video."""
        video_path = str(tmp_path / "test.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(video_path, fourcc, 30.0, (320, 240))

        # Write 150 frames (5 seconds): varied content to avoid black frame detection
        for i in range(150):
            frame = np.full((240, 320, 3), (i % 256, (i * 2) % 256, (i * 3) % 256), dtype=np.uint8)
            cv2.rectangle(frame, (10 + i, 10), (50 + i, 50), (255, 255, 255), 2)
            writer.write(frame)
        writer.release()
        return video_path

    def test_scanner_extracts_metadata(self, test_video):
        scanner = VideoScanner()
        meta = scanner.extract_cv2_metadata(test_video)
        assert meta is not None
        assert meta['width'] == 320
        assert meta['height'] == 240
        assert meta['fps'] == 30.0
        assert meta['frame_count'] == 150
        assert abs(meta['duration'] - 5.0) < 0.5

    def test_full_scan_returns_streams(self, test_video):
        scanner = VideoScanner()
        meta = scanner.scan(test_video)
        assert meta is not None
        assert meta['width'] == 320
        assert meta['height'] == 240
        assert meta['filesize'] > 0
        assert isinstance(meta['video_streams'], list)
        assert isinstance(meta['audio_streams'], list)

    def test_screenshot_sheet_generates(self, test_video):
        scanner = VideoScanner()
        meta = scanner.scan(test_video)
        assert meta is not None

        gen = ScreenshotSheetGenerator()
        settings = {
            'rows': 2, 'cols': 2,
            'show_timestamps': True,
            'show_ms': False,
            'show_frame_number': False,
            'font_family': 'monospace',
            'font_color': '#ffffff',
            'bg_color': '#000000',
        }
        sheet = gen.generate(test_video, meta, settings, header_template='Test: #width#x#height#')
        assert sheet is not None
        assert sheet.width >= 640  # 2 cols * 320
        assert sheet.height > 480  # header + 2 rows * 240

    def test_full_pipeline_scan_to_sheet_to_save(self, test_video):
        """Verify scan -> screenshot sheet -> save works end to end."""
        scanner = VideoScanner()
        meta = scanner.scan(test_video)

        gen = ScreenshotSheetGenerator()
        settings = {'rows': 2, 'cols': 2, 'show_timestamps': True}
        sheet = gen.generate(test_video, meta, settings)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            sheet.save(f.name)
            assert os.path.getsize(f.name) > 0
            os.unlink(f.name)

    def test_video_strategy_integration(self, test_video):
        """Verify VideoStrategy works end-to-end."""
        from unittest.mock import MagicMock
        from src.core.media_strategy import VideoStrategy

        strategy = VideoStrategy()

        # Test scan
        meta = strategy.scan(test_video)
        assert meta is not None
        assert meta['width'] == 320

        # Test placeholders
        item = MagicMock()
        item.path = test_video
        item.video_metadata = meta
        placeholders = strategy.get_template_placeholders(item)
        assert placeholders['resolution'] == '320x240'
        assert placeholders['filename'] == 'test.mp4'
