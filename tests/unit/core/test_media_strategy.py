"""Tests for MediaStrategy ABC and factory."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from src.core.media_strategy import (
    MediaStrategy,
    ImageStrategy,
    VideoStrategy,
    create_media_strategy,
)


class TestMediaStrategyABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            MediaStrategy()

    def test_has_required_methods(self):
        methods = ['scan', 'prepare_upload', 'generate_primary_content', 'get_template_placeholders']
        for method in methods:
            assert hasattr(MediaStrategy, method)


class TestStrategyStubs:
    """Concrete strategies raise NotImplementedError until wired."""

    def test_image_strategy_methods_raise(self):
        s = ImageStrategy()
        with pytest.raises(NotImplementedError):
            s.scan("/tmp")
        with pytest.raises(NotImplementedError):
            s.prepare_upload(None, {})
        with pytest.raises(NotImplementedError):
            s.generate_primary_content(None, {})
        with pytest.raises(NotImplementedError):
            s.get_template_placeholders(None)

    def test_video_strategy_prepare_upload_raises(self):
        s = VideoStrategy()
        with pytest.raises(NotImplementedError):
            s.prepare_upload(None, {})


class TestFactory:
    def test_image_returns_image_strategy(self):
        strategy = create_media_strategy("image")
        assert isinstance(strategy, ImageStrategy)

    def test_video_returns_video_strategy(self):
        strategy = create_media_strategy("video")
        assert isinstance(strategy, VideoStrategy)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown media type"):
            create_media_strategy("audio")


class TestVideoStrategyScan:
    """VideoStrategy.scan delegates to VideoScanner."""

    @patch('src.processing.video_scanner.VideoScanner')
    def test_scan_delegates_to_video_scanner(self, mock_scanner_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = {'width': 1920, 'height': 1080}
        mock_scanner_cls.return_value = mock_scanner

        strategy = VideoStrategy()
        result = strategy.scan('/tmp/video.mp4')

        mock_scanner.scan.assert_called_once_with('/tmp/video.mp4')
        assert result == {'width': 1920, 'height': 1080}

    @patch('src.processing.video_scanner.VideoScanner')
    def test_scan_returns_none_on_failure(self, mock_scanner_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = None
        mock_scanner_cls.return_value = mock_scanner

        strategy = VideoStrategy()
        result = strategy.scan('/tmp/bad.mp4')

        assert result is None


class TestVideoStrategyPlaceholders:
    def test_basic_placeholders(self):
        item = MagicMock()
        item.path = "/tmp/test_video.mp4"
        item.video_metadata = {
            'width': 1920,
            'height': 1080,
            'fps': 30.0,
            'duration': 300.0,
            'filesize': 1500000000,
            'video_streams': [{'format': 'H.264'}],
            'audio_streams': [
                {'format': 'AAC', 'channels': 2, 'sampling_rate': 48000, 'bit_rate': 128000},
            ],
        }

        strategy = VideoStrategy()
        placeholders = strategy.get_template_placeholders(item)

        assert placeholders['filename'] == 'test_video.mp4'
        assert placeholders['duration'] == '5:00'
        assert placeholders['resolution'] == '1920x1080'
        assert placeholders['video_codec'] == 'H.264'
        assert placeholders['audio_codec'] == 'AAC'
        assert 'audio_track_1' in placeholders
        assert placeholders['audio_track_1'] == 'AAC: 2-CH 48000Hz 128000 bps'
        assert placeholders['audio_tracks'] == 'AAC: 2-CH 48000Hz 128000 bps'

    def test_empty_metadata(self):
        item = MagicMock()
        item.path = "/tmp/empty.mp4"
        item.video_metadata = {}

        strategy = VideoStrategy()
        placeholders = strategy.get_template_placeholders(item)

        assert placeholders['filename'] == 'empty.mp4'
        assert placeholders['video_codec'] == ''
        assert placeholders['audio_codec'] == ''
        assert placeholders['audio_tracks'] == ''
        assert placeholders['duration'] == '0:00'
        assert placeholders['resolution'] == 'x'

    def test_none_metadata(self):
        item = MagicMock()
        item.path = "/tmp/none.mp4"
        item.video_metadata = None

        strategy = VideoStrategy()
        placeholders = strategy.get_template_placeholders(item)

        assert placeholders['filename'] == 'none.mp4'
        assert placeholders['video_codec'] == ''
        assert placeholders['audio_tracks'] == ''

    def test_multiple_audio_tracks(self):
        item = MagicMock()
        item.path = "/tmp/multi_audio.mkv"
        item.video_metadata = {
            'video_streams': [{'format': 'HEVC'}],
            'audio_streams': [
                {'format': 'AAC', 'channels': 2, 'sampling_rate': 48000, 'bit_rate': 128000},
                {'format': 'DTS', 'channels': 6, 'sampling_rate': 48000, 'bit_rate': 1509000},
            ],
        }

        strategy = VideoStrategy()
        placeholders = strategy.get_template_placeholders(item)

        assert placeholders['audio_track_1'] == 'AAC: 2-CH 48000Hz 128000 bps'
        assert placeholders['audio_track_2'] == 'DTS: 6-CH 48000Hz 1509000 bps'
        assert 'AAC: 2-CH 48000Hz 128000 bps' in placeholders['audio_tracks']
        assert 'DTS: 6-CH 48000Hz 1509000 bps' in placeholders['audio_tracks']

    def test_missing_audio_track_fields(self):
        """Audio tracks with missing fields use fallback values."""
        item = MagicMock()
        item.path = "/tmp/sparse.mp4"
        item.video_metadata = {
            'video_streams': [],
            'audio_streams': [{'format': 'FLAC'}],
        }

        strategy = VideoStrategy()
        placeholders = strategy.get_template_placeholders(item)

        assert placeholders['audio_track_1'] == 'FLAC: ?-CH ?Hz ? bps'


class TestVideoStrategyDuration:
    def test_format_duration_hours(self):
        assert VideoStrategy._format_duration(3661) == "1:01:01"

    def test_format_duration_minutes(self):
        assert VideoStrategy._format_duration(125) == "2:05"

    def test_format_duration_zero(self):
        assert VideoStrategy._format_duration(0) == "0:00"

    def test_format_duration_exactly_one_hour(self):
        assert VideoStrategy._format_duration(3600) == "1:00:00"

    def test_format_duration_negative_clamps_to_zero(self):
        assert VideoStrategy._format_duration(-10) == "0:00"

    def test_format_duration_fractional_truncates(self):
        assert VideoStrategy._format_duration(90.7) == "1:30"

    def test_format_duration_large(self):
        # 2 hours, 30 minutes, 45 seconds
        assert VideoStrategy._format_duration(9045) == "2:30:45"


class TestVideoStrategyGeneratePrimaryContent:
    """VideoStrategy.generate_primary_content integration with scanner and sheet generator."""

    @patch('src.processing.screenshot_sheet.ScreenshotSheetGenerator')
    @patch('src.processing.video_scanner.VideoScanner')
    def test_returns_error_when_scan_fails(self, mock_scanner_cls, mock_sheet_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = None
        mock_scanner_cls.return_value = mock_scanner

        item = MagicMock()
        item.path = '/tmp/bad_video.mp4'

        strategy = VideoStrategy()
        result = strategy.generate_primary_content(item, {})

        assert result['status'] == 'error'
        assert 'scan' in result['error'].lower()
        mock_sheet_cls.assert_not_called()

    @patch('src.processing.screenshot_sheet.ScreenshotSheetGenerator')
    @patch('src.processing.video_scanner.VideoScanner')
    def test_returns_error_when_sheet_generation_fails(self, mock_scanner_cls, mock_sheet_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = {'duration': 120, 'width': 1920, 'height': 1080}
        mock_scanner_cls.return_value = mock_scanner

        mock_generator = MagicMock()
        mock_generator.generate.return_value = None
        mock_sheet_cls.return_value = mock_generator

        item = MagicMock()
        item.path = '/tmp/video.mp4'

        strategy = VideoStrategy()
        result = strategy.generate_primary_content(item, {})

        assert result['status'] == 'error'
        assert 'screenshot' in result['error'].lower()

    @patch('src.processing.screenshot_sheet.ScreenshotSheetGenerator')
    @patch('src.processing.video_scanner.VideoScanner')
    def test_success_returns_sheet_path_and_metadata(self, mock_scanner_cls, mock_sheet_cls):
        metadata = {'duration': 120, 'width': 1920, 'height': 1080}
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = metadata
        mock_scanner_cls.return_value = mock_scanner

        mock_sheet = MagicMock()
        mock_generator = MagicMock()
        mock_generator.generate.return_value = mock_sheet
        mock_sheet_cls.return_value = mock_generator

        item = MagicMock()
        item.path = '/tmp/video.mp4'
        item.name = 'video'

        strategy = VideoStrategy()
        result = strategy.generate_primary_content(item, {})

        assert result['status'] == 'success'
        assert 'screenshot_sheet_path' in result
        assert result['screenshot_sheet_path'].endswith('_sheet.png')
        assert result['metadata'] == metadata
        mock_sheet.save.assert_called_once()

    @patch('src.processing.screenshot_sheet.ScreenshotSheetGenerator')
    @patch('src.processing.video_scanner.VideoScanner')
    def test_jpg_output_format(self, mock_scanner_cls, mock_sheet_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = {'duration': 60}
        mock_scanner_cls.return_value = mock_scanner

        mock_sheet = MagicMock()
        mock_generator = MagicMock()
        mock_generator.generate.return_value = mock_sheet
        mock_sheet_cls.return_value = mock_generator

        item = MagicMock()
        item.path = '/tmp/video.mp4'
        item.name = 'video'

        strategy = VideoStrategy()
        result = strategy.generate_primary_content(item, {'output_format': 'JPG'})

        assert result['status'] == 'success'
        assert result['screenshot_sheet_path'].endswith('_sheet.jpg')

    @patch('src.processing.screenshot_sheet.ScreenshotSheetGenerator')
    @patch('src.processing.video_scanner.VideoScanner')
    def test_header_template_passed_to_generator(self, mock_scanner_cls, mock_sheet_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = {'duration': 60}
        mock_scanner_cls.return_value = mock_scanner

        mock_generator = MagicMock()
        mock_generator.generate.return_value = MagicMock()
        mock_sheet_cls.return_value = mock_generator

        item = MagicMock()
        item.path = '/tmp/video.mp4'
        item.name = 'video'

        settings = {'image_overlay_template': 'File: #filename#'}
        strategy = VideoStrategy()
        strategy.generate_primary_content(item, settings)

        mock_generator.generate.assert_called_once()
        call_args = mock_generator.generate.call_args
        assert call_args[0][3] == 'File: #filename#'
