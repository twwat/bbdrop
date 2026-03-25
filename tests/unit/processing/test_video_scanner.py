"""Tests for VideoScanner metadata extraction."""
import pytest
from unittest.mock import patch, MagicMock
from src.processing.video_scanner import VideoScanner


class TestVideoScannerMetadata:
    """Test metadata extraction with mocked OpenCV and pymediainfo."""

    def _mock_cv2_capture(self, width=1920, height=1080, fps=30.0, frame_count=9000):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            3: float(width),   # CAP_PROP_FRAME_WIDTH
            4: float(height),  # CAP_PROP_FRAME_HEIGHT
            5: fps,            # CAP_PROP_FPS
            7: float(frame_count),  # CAP_PROP_FRAME_COUNT
        }.get(prop, 0.0)
        cap.release.return_value = None
        return cap

    @patch('src.processing.video_scanner.cv2')
    def test_extracts_basic_metadata(self, mock_cv2):
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.VideoCapture.return_value = self._mock_cv2_capture()

        scanner = VideoScanner()
        meta = scanner.extract_cv2_metadata("/fake/video.mp4")

        assert meta['width'] == 1920
        assert meta['height'] == 1080
        assert meta['fps'] == 30.0
        assert meta['frame_count'] == 9000
        assert meta['duration'] == 300.0  # 9000 / 30

    @patch('src.processing.video_scanner.cv2')
    def test_handles_unopenable_file(self, mock_cv2):
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = cap

        scanner = VideoScanner()
        meta = scanner.extract_cv2_metadata("/fake/broken.mp4")
        assert meta is None

    @patch('src.processing.video_scanner.cv2')
    def test_handles_zero_fps(self, mock_cv2):
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.VideoCapture.return_value = self._mock_cv2_capture(fps=0.0)

        scanner = VideoScanner()
        meta = scanner.extract_cv2_metadata("/fake/video.mp4")

        assert meta['duration'] == 0.0

    @patch('src.processing.video_scanner.cv2')
    def test_release_called_on_success(self, mock_cv2):
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        cap = self._mock_cv2_capture()
        mock_cv2.VideoCapture.return_value = cap

        scanner = VideoScanner()
        scanner.extract_cv2_metadata("/fake/video.mp4")

        cap.release.assert_called_once()

    @patch('src.processing.video_scanner.cv2')
    def test_release_called_on_failure(self, mock_cv2):
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = cap

        scanner = VideoScanner()
        scanner.extract_cv2_metadata("/fake/broken.mp4")

        cap.release.assert_called_once()


class TestVideoScannerMediaInfo:
    """Test pymediainfo stream extraction."""

    def _make_track(self, track_type, **kwargs):
        track = MagicMock()
        track.track_type = track_type
        for k, v in kwargs.items():
            setattr(track, k, v)
        return track

    @patch('src.processing.video_scanner.MediaInfo')
    def test_extracts_video_stream(self, mock_mediainfo):
        video_track = self._make_track(
            'Video',
            codec_id='V_MPEG4/ISO/AVC',
            format='AVC',
            width=1920,
            height=1080,
            frame_rate=30.0,
            bit_rate=5000000,
            color_space='YUV',
            chroma_subsampling='4:2:0',
        )
        mock_mediainfo.parse.return_value = MagicMock(tracks=[video_track])

        scanner = VideoScanner()
        streams = scanner.extract_mediainfo("/fake/video.mp4")

        assert len(streams['video']) == 1
        assert streams['video'][0]['format'] == 'AVC'
        assert streams['video'][0]['width'] == 1920
        assert streams['video'][0]['codec_id'] == 'V_MPEG4/ISO/AVC'
        assert streams['video'][0]['bit_rate'] == 5000000

    @patch('src.processing.video_scanner.MediaInfo')
    def test_extracts_multiple_audio_streams(self, mock_mediainfo):
        audio1 = self._make_track(
            'Audio', format='AAC', channels=2, bit_depth=16,
            sampling_rate=44100, bit_rate=128000,
        )
        audio2 = self._make_track(
            'Audio', format='AC-3', channels=6, bit_depth=16,
            sampling_rate=48000, bit_rate=384000,
        )
        mock_mediainfo.parse.return_value = MagicMock(tracks=[audio1, audio2])

        scanner = VideoScanner()
        streams = scanner.extract_mediainfo("/fake/video.mkv")

        assert len(streams['audio']) == 2
        assert streams['audio'][0]['format'] == 'AAC'
        assert streams['audio'][1]['format'] == 'AC-3'
        assert streams['audio'][1]['channels'] == 6

    @patch('src.processing.video_scanner.MediaInfo')
    def test_ignores_non_av_tracks(self, mock_mediainfo):
        general_track = self._make_track('General', format='Matroska')
        menu_track = self._make_track('Menu')
        video_track = self._make_track('Video', format='HEVC')
        mock_mediainfo.parse.return_value = MagicMock(
            tracks=[general_track, menu_track, video_track]
        )

        scanner = VideoScanner()
        streams = scanner.extract_mediainfo("/fake/video.mkv")

        assert len(streams['video']) == 1
        assert len(streams['audio']) == 0

    @patch('src.processing.video_scanner.MediaInfo')
    def test_empty_tracks(self, mock_mediainfo):
        mock_mediainfo.parse.return_value = MagicMock(tracks=[])

        scanner = VideoScanner()
        streams = scanner.extract_mediainfo("/fake/video.mp4")

        assert streams['video'] == []
        assert streams['audio'] == []


class TestVideoScannerFullScan:
    """Test the combined scan() method."""

    @patch.object(VideoScanner, 'extract_mediainfo')
    @patch.object(VideoScanner, 'extract_cv2_metadata')
    @patch('os.path.getsize', return_value=1_500_000_000)
    def test_scan_combines_cv2_and_mediainfo(self, mock_size, mock_cv2, mock_mi):
        mock_cv2.return_value = {
            'width': 1920, 'height': 1080, 'fps': 24.0,
            'frame_count': 7200, 'duration': 300.0,
        }
        mock_mi.return_value = {
            'video': [{'format': 'HEVC', 'width': 1920, 'height': 1080,
                        'frame_rate': 24.0, 'bit_rate': 4000000,
                        'color_space': 'YUV', 'chroma_subsampling': '4:2:0'}],
            'audio': [{'format': 'AAC', 'channels': 2, 'bit_depth': 16,
                        'sampling_rate': 48000, 'bit_rate': 128000}],
        }

        scanner = VideoScanner()
        result = scanner.scan("/fake/video.mp4")

        assert result['width'] == 1920
        assert result['height'] == 1080
        assert result['duration'] == 300.0
        assert result['filesize'] == 1_500_000_000
        assert result['video_streams'][0]['format'] == 'HEVC'
        assert result['audio_streams'][0]['format'] == 'AAC'

    @patch.object(VideoScanner, 'extract_mediainfo')
    @patch.object(VideoScanner, 'extract_cv2_metadata')
    def test_scan_returns_none_when_cv2_fails(self, mock_cv2, mock_mi):
        mock_cv2.return_value = None

        scanner = VideoScanner()
        result = scanner.scan("/fake/broken.mp4")

        assert result is None
        mock_mi.assert_not_called()
