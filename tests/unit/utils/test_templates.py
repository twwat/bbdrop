"""Tests for template processing and video placeholder resolution."""

import pytest

from src.utils.templates import apply_template, process_conditionals, _camel_to_snake, process_flag_tags


class TestCamelToSnake:
    """Test the camelCase to snake_case helper."""

    def test_simple_camel(self):
        assert _camel_to_snake('downloadLinks') == 'download_links'

    def test_single_word(self):
        assert _camel_to_snake('ext1') == 'ext1'

    def test_multiple_humps(self):
        assert _camel_to_snake('videoDetails') == 'video_details'

    def test_already_snake(self):
        assert _camel_to_snake('host_links') == 'host_links'

    def test_all_lowercase(self):
        assert _camel_to_snake('filename') == 'filename'


class TestApplyTemplateBasic:
    """Test basic placeholder replacement in apply_template."""

    def test_folder_name_replaced(self):
        result = apply_template("#folderName#", {'folder_name': 'MyGallery'})
        assert result == 'MyGallery'

    def test_all_images_replaced(self):
        result = apply_template("#allImages#", {'all_images': '[img]a.jpg[/img]'})
        assert result == '[img]a.jpg[/img]'

    def test_missing_data_resolves_to_empty(self):
        result = apply_template("#folderName# #galleryLink#", {'folder_name': 'test'})
        assert result == 'test '

    def test_multiple_placeholders(self):
        template = "#folderName# - #extension# - #pictureCount#"
        data = {'folder_name': 'Gallery', 'extension': 'JPG', 'picture_count': 10}
        result = apply_template(template, data)
        assert result == 'Gallery - JPG - 10'


class TestConditionals:
    """Test conditional block processing."""

    def test_conditional_true(self):
        template = "[if ext1]has ext1: #ext1#[/if]"
        result = apply_template(template, {'ext1': 'hello'})
        assert 'has ext1: hello' in result

    def test_conditional_false(self):
        template = "[if ext1]has ext1[/if]"
        result = apply_template(template, {})
        assert 'has ext1' not in result

    def test_conditional_with_else(self):
        template = "[if galleryLink]link: #galleryLink#[else]no link[/if]"
        result = apply_template(template, {'gallery_link': 'http://example.com'})
        assert 'link: http://example.com' in result

    def test_conditional_with_else_false_branch(self):
        template = "[if galleryLink]link: #galleryLink#[else]no link[/if]"
        result = apply_template(template, {})
        assert 'no link' in result

    def test_conditional_camel_to_snake_fallback(self):
        """Conditionals use camelCase names but data uses snake_case keys."""
        template = "[if hostLinks]links: #hostLinks#[/if]"
        result = apply_template(template, {'host_links': 'http://dl.example.com'})
        assert 'links: http://dl.example.com' in result


class TestVideoPlaceholders:
    def test_video_details_placeholder_resolved(self):
        template = "Title\n#videoDetails#\n#allImages#"
        data = {
            'video_details': 'Duration: 5:00\nCodec: H.264',
            'all_images': '[img]thumb.jpg[/img]',
        }
        result = apply_template(template, data)
        assert 'Duration: 5:00' in result
        assert 'Codec: H.264' in result

    def test_video_placeholders_empty_for_images(self):
        template = "#folderName#\n#videoDetails#\n#allImages#"
        data = {
            'folder_name': 'my_gallery',
            'all_images': '[img]thumb.jpg[/img]',
        }
        result = apply_template(template, data)
        assert 'my_gallery' in result
        assert '#videoDetails#' not in result

    def test_download_links_placeholder(self):
        template = "#folderName#\n[if downloadLinks]Links: #downloadLinks#[/if]"
        data = {
            'folder_name': 'my_video',
            'download_links': 'https://example.com/dl/video.mp4',
        }
        result = apply_template(template, data)
        assert 'Links: https://example.com/dl/video.mp4' in result

    def test_screenshot_sheet_placeholder(self):
        template = "#screenshotSheet#"
        data = {
            'screenshot_sheet': '[img]http://host.com/sheet.jpg[/img]',
        }
        result = apply_template(template, data)
        assert '[img]http://host.com/sheet.jpg[/img]' in result

    def test_individual_video_placeholders(self):
        template = "#filename# | #duration# | #resolution# | #fps# | #bitrate# | #videoCodec# | #audioCodec# | #audioTracks# | #filesize#"
        data = {
            'filename': 'video.mp4',
            'duration': '01:30:00',
            'resolution': '1920x1080',
            'fps': '23.976',
            'bitrate': '8500 kbps',
            'video_codec': 'H.265',
            'audio_codec': 'AAC',
            'audio_tracks': '2',
            'filesize': '4.2 GB',
        }
        result = apply_template(template, data)
        assert 'video.mp4' in result
        assert '01:30:00' in result
        assert '1920x1080' in result
        assert '23.976' in result
        assert '8500 kbps' in result
        assert 'H.265' in result
        assert 'AAC' in result
        assert '2' in result
        assert '4.2 GB' in result

    def test_video_placeholders_absent_resolve_empty(self):
        """Video placeholders resolve to empty strings when not in data."""
        template = "X#videoCodec#X#audioCodec#X#duration#X"
        result = apply_template(template, {})
        assert result == 'XXXX'

    def test_video_and_image_placeholders_coexist(self):
        """Video and image placeholders can appear in the same template."""
        template = "#folderName#\n#allImages#\n#videoDetails#\n#screenshotSheet#"
        data = {
            'folder_name': 'mixed',
            'all_images': '[img]thumb.jpg[/img]',
            'video_details': 'Codec: H.264',
            'screenshot_sheet': '[img]sheet.jpg[/img]',
        }
        result = apply_template(template, data)
        assert 'mixed' in result
        assert '[img]thumb.jpg[/img]' in result
        assert 'Codec: H.264' in result
        assert '[img]sheet.jpg[/img]' in result


class TestProcessFlagTags:

    def test_alpha2_uppercase(self):
        result = process_flag_tags("[flag]US[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/us.png[/IMG]"

    def test_alpha2_lowercase(self):
        result = process_flag_tags("[flag]us[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/us.png[/IMG]"

    def test_alpha3_uppercase(self):
        result = process_flag_tags("[FLAG]USA[/FLAG]")
        assert result == "[IMG]https://flagcdn.com/43x36/us.png[/IMG]"

    def test_alpha3_lowercase(self):
        result = process_flag_tags("[flag]can[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/ca.png[/IMG]"

    def test_numeric_code(self):
        result = process_flag_tags("[flag]666[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/pm.png[/IMG]"

    def test_numeric_code_padding_1_digit(self):
        result = process_flag_tags("[flag]8[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/al.png[/IMG]"

    def test_numeric_code_padding_2_digits(self):
        result = process_flag_tags("[flag]44[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/bs.png[/IMG]"

    def test_english_name_exact(self):
        result = process_flag_tags("[FLAG]canada[/FLAG]")
        assert result == "[IMG]https://flagcdn.com/43x36/ca.png[/IMG]"

    def test_english_name_mixed_case(self):
        result = process_flag_tags("[flag]CHINA[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/cn.png[/IMG]"

    def test_whitespace_trimmed(self):
        result = process_flag_tags("[FLAG] HU [/FLAG]")
        assert result == "[IMG]https://flagcdn.com/43x36/hu.png[/IMG]"

    def test_no_match_empty(self):
        result = process_flag_tags("[flag][/flag]")
        assert result == ""

    def test_no_match_invalid_name(self):
        result = process_flag_tags("[FLAG]hello[/FLAG]")
        assert result == ""

    def test_no_match_invalid_code(self):
        result = process_flag_tags("[flag]ZZ[/flag]")
        assert result == ""

    def test_no_match_partial_name(self):
        result = process_flag_tags("[FLAG]America[/FLAG]")
        assert result == ""

    def test_multiple_tags(self):
        result = process_flag_tags("[flag]us[/flag] and [flag]ca[/flag]")
        assert "[IMG]https://flagcdn.com/43x36/us.png[/IMG]" in result
        assert "[IMG]https://flagcdn.com/43x36/ca.png[/IMG]" in result

    def test_case_insensitive_tags(self):
        r1 = process_flag_tags("[flag]us[/flag]")
        r2 = process_flag_tags("[FLAG]us[/FLAG]")
        r3 = process_flag_tags("[FlaG]us[/FlAg]")
        assert r1 == r2 == r3

    def test_diacritics_stripped(self):
        result = process_flag_tags("[flag]Aland Islands[/flag]")
        assert result == "[IMG]https://flagcdn.com/43x36/ax.png[/IMG]"


def test_flag_tag_in_template_pipeline():
    template_content = "[b]Gallery[/b]\n[flag]us[/flag]\nCountry: [flag]ca[/flag]"
    data = {}

    result = apply_template(template_content, data)

    assert "[IMG]https://flagcdn.com/43x36/us.png[/IMG]" in result
    assert "[IMG]https://flagcdn.com/43x36/ca.png[/IMG]" in result
    assert "[flag]" not in result


def test_flag_tag_invalid_in_template_pipeline():
    template_content = "Gallery [flag]ZZ[/flag] done"
    data = {}

    result = apply_template(template_content, data)

    assert "[flag]" not in result
    assert "Gallery" in result
    assert "done" in result
