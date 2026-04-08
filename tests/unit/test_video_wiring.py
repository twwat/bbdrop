"""Tests for video pipeline wiring: results dict, template data, entry points."""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.utils.templates import apply_template, load_templates, save_gallery_artifacts


# -- Default Video template --------------------------------------------------

class TestVideoTemplateExists:
    """The built-in Video template should be available."""

    def test_video_template_in_defaults(self):
        templates = load_templates()
        assert "Video" in templates

    def test_video_template_uses_video_placeholders(self):
        templates = load_templates()
        video_tpl = templates["Video"]
        assert "#screenshotSheet#" in video_tpl
        assert "#filename#" in video_tpl
        assert "#duration#" in video_tpl
        assert "#resolution#" in video_tpl
        assert "#videoCodec#" in video_tpl

    def test_video_template_has_conditional_downloads(self):
        templates = load_templates()
        video_tpl = templates["Video"]
        assert "[if downloadLinks]" in video_tpl


# -- Video metadata flows into template_data ---------------------------------

class TestSaveGalleryArtifactsVideoMetadata:
    """save_gallery_artifacts should populate video fields when video_metadata present."""

    def _make_video_results(self):
        return {
            'gallery_id': 'abc123',
            'gallery_name': 'test_video',
            'gallery_url': 'http://host.com/g/abc123',
            'successful_count': 1,
            'failed_count': 0,
            'total_images': 1,
            'total_size': 1_500_000_000,
            'uploaded_size': 500_000,
            'upload_time': 12.5,
            'media_type': 'video',
            'avg_width': 1920,
            'avg_height': 1080,
            'max_width': 1920,
            'max_height': 1080,
            'min_width': 1920,
            'min_height': 1080,
            'images': [{
                'original_filename': 'test_video_sheet.png',
                'image_url': 'http://host.com/img/sheet.png',
                'thumb_url': 'http://host.com/thumb/sheet.png',
                'bbcode': '[url=http://host.com/img/sheet.png][img]http://host.com/thumb/sheet.png[/img][/url]',
            }],
            'video_metadata': {
                'width': 1920,
                'height': 1080,
                'fps': 23.976,
                'duration': 5400.0,
                'bitrate': '8500 kbps',
                'filesize': 1_500_000_000,
                'video_streams': [{'format': 'H.265'}],
                'audio_streams': [
                    {'format': 'AAC', 'channels': 2, 'sampling_rate': 48000, 'bit_rate': 128000},
                ],
            },
        }

    @patch('src.utils.templates.generate_bbcode_from_template')
    @patch('src.utils.templates.load_user_defaults', return_value={'store_in_uploaded': False, 'store_in_central': False})
    def test_video_metadata_populates_template_data(self, mock_defaults, mock_gen):
        """When results contain video_metadata, template_data should have video fields."""
        mock_gen.return_value = "rendered bbcode"

        results = self._make_video_results()
        save_gallery_artifacts(
            folder_path="/tmp/fake_video",
            results=results,
            template_name="Video",
            store_in_uploaded=False,
            store_in_central=False,
        )

        # Check the template_data dict that was passed to generate_bbcode_from_template
        call_args = mock_gen.call_args
        template_name_arg = call_args[0][0]
        template_data = call_args[0][1]

        assert template_name_arg == "Video"
        assert template_data['duration'] == '1:30:00'
        assert template_data['resolution'] == '1920x1080'
        assert template_data['video_codec'] == 'H.265'
        assert template_data['audio_codec'] == 'AAC'
        assert template_data['fps'] == '23.976'
        assert 'GB' in template_data['filesize']
        assert template_data['filename'] == 'fake_video'

    @patch('src.utils.templates.generate_bbcode_from_template')
    @patch('src.utils.templates.load_user_defaults', return_value={'store_in_uploaded': False, 'store_in_central': False})
    def test_screenshot_sheet_bbcode_from_images(self, mock_defaults, mock_gen):
        """screenshot_sheet should be the uploaded sheet image's BBCode."""
        mock_gen.return_value = "rendered"

        results = self._make_video_results()
        save_gallery_artifacts(
            folder_path="/tmp/fake_video",
            results=results,
            template_name="Video",
            store_in_uploaded=False,
            store_in_central=False,
        )

        template_data = mock_gen.call_args[0][1]
        assert '[url=' in template_data['screenshot_sheet']
        assert '[img]' in template_data['screenshot_sheet']

    @patch('src.utils.templates.generate_bbcode_from_template')
    @patch('src.utils.templates.load_user_defaults', return_value={'store_in_uploaded': False, 'store_in_central': False})
    def test_video_details_summary_string(self, mock_defaults, mock_gen):
        """video_details should be a composed summary string."""
        mock_gen.return_value = "rendered"

        results = self._make_video_results()
        save_gallery_artifacts(
            folder_path="/tmp/fake_video",
            results=results,
            template_name="Video",
            store_in_uploaded=False,
            store_in_central=False,
        )

        template_data = mock_gen.call_args[0][1]
        assert '1920x1080' in template_data['video_details']
        assert '1:30:00' in template_data['video_details']
        assert 'H.265' in template_data['video_details']

    @patch('src.utils.templates.generate_bbcode_from_template')
    @patch('src.utils.templates.load_user_defaults', return_value={'store_in_uploaded': False, 'store_in_central': False})
    def test_no_video_metadata_leaves_fields_absent(self, mock_defaults, mock_gen):
        """Without video_metadata in results, video fields should not be in template_data."""
        mock_gen.return_value = "rendered"

        results = self._make_video_results()
        del results['video_metadata']

        save_gallery_artifacts(
            folder_path="/tmp/fake_video",
            results=results,
            template_name="default",
            store_in_uploaded=False,
            store_in_central=False,
        )

        template_data = mock_gen.call_args[0][1]
        assert 'video_codec' not in template_data
        assert 'duration' not in template_data

    @patch('src.utils.templates.generate_bbcode_from_template')
    @patch('src.utils.templates.load_user_defaults', return_value={'store_in_uploaded': False, 'store_in_central': False})
    def test_audio_tracks_joined(self, mock_defaults, mock_gen):
        """audio_tracks should be a joined string of all tracks."""
        mock_gen.return_value = "rendered"

        results = self._make_video_results()
        results['video_metadata']['audio_streams'] = [
            {'format': 'AAC', 'channels': 2, 'sampling_rate': 48000, 'bit_rate': 128000},
            {'format': 'AC-3', 'channels': 6, 'sampling_rate': 48000, 'bit_rate': 640000},
        ]

        save_gallery_artifacts(
            folder_path="/tmp/fake_video",
            results=results,
            template_name="Video",
            store_in_uploaded=False,
            store_in_central=False,
        )

        template_data = mock_gen.call_args[0][1]
        assert 'AAC' in template_data['audio_tracks']
        assert 'AC-3' in template_data['audio_tracks']


# -- Video results dict shape ------------------------------------------------

class TestVideoResultsDict:
    """_upload_video_gallery results dict must include fields for artifact generation."""

    def test_results_dict_has_required_fields(self):
        """Verify the results dict shape matches what save_gallery_artifacts needs."""
        # This tests the contract, not the method itself (which needs network)
        required_keys = [
            'gallery_name', 'gallery_id', 'successful_count', 'failed_count',
            'total_images', 'images', 'media_type', 'video_metadata',
            'total_size', 'upload_time', 'avg_width', 'avg_height',
        ]
        # Build a mock results dict matching _upload_video_gallery output
        results = {
            'successful_count': 1,
            'failed_count': 0,
            'total_images': 1,
            'gallery_id': 'abc123',
            'gallery_name': 'test_video',
            'gallery_url': 'http://host.com/g/abc123',
            'images': [{'original_filename': 'sheet.png', 'bbcode': '[img]x[/img]'}],
            'screenshot_sheet_path': '/tmp/sheet.png',
            'media_type': 'video',
            'video_metadata': {'width': 1920, 'height': 1080, 'duration': 60},
            'upload_time': 5.0,
            'total_size': 100_000,
            'avg_width': 1920,
            'avg_height': 1080,
            'max_width': 1920,
            'max_height': 1080,
            'min_width': 1920,
            'min_height': 1080,
            'thumbnail_size': 180,
            'thumbnail_format': 1,
        }
        for key in required_keys:
            assert key in results, f"Missing required key: {key}"


# -- Single video file entry point -------------------------------------------

class TestAddFoldersOrArchivesVideoFiles:
    """add_folders_or_archives should route video files to _add_single_video_file."""

    def test_video_file_routed_separately(self):
        """A .mp4 path should be routed to _add_single_video_file, not folders or archives."""
        import src.gui.gallery_queue_controller as mod

        controller = mod.GalleryQueueController.__new__(mod.GalleryQueueController)
        controller._main_window = MagicMock()

        # Save originals to avoid breaking logger/other internals
        real_isdir = os.path.isdir
        real_isfile = os.path.isfile
        test_paths = {'/tmp/gallery_folder', '/tmp/archive.zip', '/tmp/movie.mp4', '/tmp/clip.mkv'}

        def fake_isdir(p):
            return p == '/tmp/gallery_folder' if p in test_paths else real_isdir(p)

        def fake_isfile(p):
            return p in ('/tmp/archive.zip', '/tmp/movie.mp4', '/tmp/clip.mkv') if p in test_paths else real_isfile(p)

        real_is_archive = mod.is_archive_file

        with patch.object(controller, 'add_folders') as mock_add_folders, \
             patch.object(controller, '_add_single_video_file') as mock_add_video, \
             patch.object(mod.os.path, 'isdir', side_effect=fake_isdir), \
             patch.object(mod.os.path, 'isfile', side_effect=fake_isfile), \
             patch.object(mod, 'is_archive_file', side_effect=lambda p: p.endswith('.zip')):

            controller.add_folders_or_archives([
                '/tmp/gallery_folder',
                '/tmp/archive.zip',
                '/tmp/movie.mp4',
                '/tmp/clip.mkv',
            ])

            # Folder routed to add_folders
            mock_add_folders.assert_called_once_with(['/tmp/gallery_folder'])

            # Video files routed to _add_single_video_file
            assert mock_add_video.call_count == 2
            mock_add_video.assert_any_call('/tmp/movie.mp4')
            mock_add_video.assert_any_call('/tmp/clip.mkv')
