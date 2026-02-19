#!/usr/bin/env python3
"""
Comprehensive test suite for format_utils.py
Testing formatting functions for binary sizes, rates, durations, and string utilities
"""

import pytest
from src.utils.format_utils import (
    timestamp,
    format_binary_size,
    format_binary_rate,
    format_duration,
    sanitize_gallery_name,
    truncate_string,
    format_percentage
)

# Non-breaking space character used by format functions for typography
# Prevents line wrapping between numbers and units in GUI displays
NBSP = "\u00A0"


class TestTimestamp:
    """Test timestamp generation"""

    def test_timestamp_format(self):
        """Test timestamp returns HH:MM:SS format"""
        ts = timestamp()
        assert len(ts) == 8
        assert ts[2] == ":"
        assert ts[5] == ":"
        assert ts.count(":") == 2

    def test_timestamp_valid_time(self):
        """Test timestamp contains valid time components"""
        ts = timestamp()
        parts = ts.split(":")
        hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
        assert 0 <= hours <= 23
        assert 0 <= minutes <= 59
        assert 0 <= seconds <= 59


class TestFormatBinarySize:
    """Test binary size formatting with 1024 step"""

    @pytest.mark.parametrize("bytes_value,expected", [
        # Bytes (no decimals)
        (0, f"0{NBSP}B"),
        (1, f"1{NBSP}B"),
        (512, f"512{NBSP}B"),
        (1023, f"1023{NBSP}B"),
        # KiB
        (1024, f"1.0{NBSP}KiB"),
        (2048, f"2.0{NBSP}KiB"),
        (1536, f"1.5{NBSP}KiB"),
        # MiB
        (1048576, f"1.0{NBSP}MiB"),
        (5242880, f"5.0{NBSP}MiB"),
        (10485760, f"10.0{NBSP}MiB"),
        # GiB
        (1073741824, f"1.0{NBSP}GiB"),
        (5368709120, f"5.0{NBSP}GiB"),
        # TiB
        (1099511627776, f"1.0{NBSP}TiB"),
        # PiB (max unit)
        (1125899906842624, f"1.0{NBSP}PiB"),
    ])
    def test_standard_sizes(self, bytes_value, expected):
        """Test standard binary size conversions"""
        assert format_binary_size(bytes_value) == expected

    @pytest.mark.parametrize("bytes_value,precision,expected", [
        (1536, 2, f"1.50{NBSP}KiB"),
        (1536, 0, f"2{NBSP}KiB"),
        (1572864, 3, f"1.500{NBSP}MiB"),
        (5500000, 2, f"5.25{NBSP}MiB"),
    ])
    def test_precision_control(self, bytes_value, precision, expected):
        """Test precision parameter controls decimal places"""
        assert format_binary_size(bytes_value, precision) == expected

    @pytest.mark.parametrize("invalid_input", [
        None,
        "",
        "not a number",
        [],
    ])
    def test_invalid_input_returns_zero(self, invalid_input):
        """Test invalid inputs return 0 B"""
        assert format_binary_size(invalid_input) == f"0{NBSP}B"

    def test_negative_value_returns_zero(self):
        """Test negative values treated as zero"""
        assert format_binary_size(-1024) == f"0{NBSP}B"

    def test_float_input(self):
        """Test float inputs are handled"""
        assert format_binary_size(1024.5) == f"1.0{NBSP}KiB"
        assert format_binary_size(2048.9) == f"2.0{NBSP}KiB"

    def test_very_large_number(self):
        """Test handling of numbers beyond PiB"""
        # 2 PiB
        huge_number = 2 * 1125899906842624
        result = format_binary_size(huge_number)
        assert "PiB" in result
        assert "2.0" in result


class TestFormatBinaryRate:
    """Test transfer rate formatting"""

    @pytest.mark.parametrize("kib_per_s,expected", [
        # KiB/s
        (0, f"0.0{NBSP}KiB/s"),
        (1, f"1.0{NBSP}KiB/s"),
        (100, f"100.0{NBSP}KiB/s"),
        (1023, f"1023.0{NBSP}KiB/s"),
        # MiB/s
        (1024, f"1.0{NBSP}MiB/s"),
        (2048, f"2.0{NBSP}MiB/s"),
        (5120, f"5.0{NBSP}MiB/s"),
        # GiB/s
        (1048576, f"1.0{NBSP}GiB/s"),
        # TiB/s
        (1073741824, f"1.0{NBSP}TiB/s"),
    ])
    def test_standard_rates(self, kib_per_s, expected):
        """Test standard transfer rate conversions"""
        assert format_binary_rate(kib_per_s) == expected

    @pytest.mark.parametrize("kib_per_s,precision,expected", [
        (1536, 2, f"1.50{NBSP}MiB/s"),
        (1536, 0, f"2{NBSP}MiB/s"),
        (512.5, 3, f"512.500{NBSP}KiB/s"),
    ])
    def test_precision_control(self, kib_per_s, precision, expected):
        """Test precision parameter"""
        assert format_binary_rate(kib_per_s, precision) == expected

    @pytest.mark.parametrize("invalid_input", [
        None,
        "",
        "invalid",
    ])
    def test_invalid_input(self, invalid_input):
        """Test invalid inputs return 0.0 KiB/s"""
        assert format_binary_rate(invalid_input) == f"0.0{NBSP}KiB/s"

    def test_float_input(self):
        """Test float rate values"""
        assert format_binary_rate(1024.5) == f"1.0{NBSP}MiB/s"


class TestFormatDuration:
    """Test duration formatting"""

    @pytest.mark.parametrize("seconds,expected", [
        # Edge cases
        (0, "0s"),
        (1, "1s"),
        # Seconds only
        (30, "30s"),
        (59, "59s"),
        # Minutes and seconds
        (60, "1m"),
        (90, "1m 30s"),
        (119, "1m 59s"),
        (120, "2m"),
        # Hours, minutes, seconds
        (3600, "1h"),
        (3661, "1h 1m 1s"),
        (7200, "2h"),
        (7260, "2h 1m"),
        (7261, "2h 1m 1s"),
        # Days
        (86400, "1d"),
        (90000, "1d 1h"),
        (172800, "2d"),
        (176461, "2d 1h 1m 1s"),
        (604800, "7d"),
        (694861, "8d 1h 1m 1s"),
    ])
    def test_duration_formatting(self, seconds, expected):
        """Test various duration values"""
        assert format_duration(seconds) == expected

    def test_negative_duration(self):
        """Test negative duration returns 0s"""
        assert format_duration(-10) == "0s"
        assert format_duration(-3600) == "0s"

    @pytest.mark.parametrize("seconds,expected", [
        (3599, "59m 59s"),
        (3665, "1h 1m 5s"),
        (5430, "1h 30m 30s"),
    ])
    def test_complex_durations(self, seconds, expected):
        """Test complex duration combinations"""
        assert format_duration(seconds) == expected

    def test_float_seconds(self):
        """Test float seconds are truncated to int"""
        assert format_duration(90.9) == "1m 30s"
        assert format_duration(3661.5) == "1h 1m 1s"


class TestSanitizeGalleryName:
    """Test gallery name sanitization"""

    @pytest.mark.parametrize("input_name,expected", [
        # Valid names (unchanged)
        ("My Gallery", "My Gallery"),
        ("Photos_2024", "Photos_2024"),
        ("test-gallery", "test-gallery"),
        # Invalid characters replaced
        ("gallery<test>", "gallery_test_"),
        ('file:name', "file_name"),
        ('path/to\\gallery', "path_to_gallery"),
        ('question?mark', "question_mark"),
        ('pipe|name', "pipe_name"),
        ('star*name', "star_name"),
        ('quote"name', "quote_name"),
        # Empty and whitespace
        ("", "untitled"),
        ("   ", "untitled"),
        # Dots and spaces trimmed
        ("  gallery  ", "gallery"),
        ("...gallery...", "gallery"),
        ("  ...  ", "untitled"),
        # Control characters removed
        ("test\x00name", "testname"),
        ("gallery\n\r\t", "gallery"),
    ])
    def test_sanitization(self, input_name, expected):
        """Test various sanitization scenarios"""
        assert sanitize_gallery_name(input_name) == expected

    def test_empty_input(self):
        """Test empty string returns default"""
        assert sanitize_gallery_name("") == "untitled"

    def test_none_input(self):
        """Test None returns default"""
        assert sanitize_gallery_name(None) == "untitled gallery"

    def test_long_name_truncated(self):
        """Test names over 200 chars are truncated"""
        long_name = "a" * 250
        result = sanitize_gallery_name(long_name)
        assert len(result) == 200
        assert result == "a" * 200

    def test_all_invalid_chars(self):
        """Test name with only invalid chars"""
        assert sanitize_gallery_name('<>:"/\\|?*') == "untitled"

    def test_unicode_preserved(self):
        """Test unicode characters are preserved"""
        result = sanitize_gallery_name("Gallery 日本語 中文")
        assert "日本語" in result
        assert "中文" in result

    @pytest.mark.parametrize("input_name", [
        "Gallery<>Test",
        "My:Gallery/Name",
        'Test"Gallery"',
    ])
    def test_partial_sanitization(self, input_name):
        """Test names with mix of valid and invalid chars"""
        result = sanitize_gallery_name(input_name)
        # Should not contain invalid chars
        for char in '<>:"/\\|?*':
            assert char not in result
        # Should contain underscores as replacements
        assert "_" in result


class TestTruncateString:
    """Test string truncation"""

    @pytest.mark.parametrize("text,max_length,expected", [
        # No truncation needed
        ("short", 10, "short"),
        ("exact", 5, "exact"),
        # Truncation with default suffix
        ("This is a long string", 10, "This is..."),
        ("Testing truncation", 15, "Testing trun..."),
        # Edge cases
        ("abc", 3, "abc"),
        ("abcd", 3, "..."),
    ])
    def test_truncation(self, text, max_length, expected):
        """Test string truncation with default suffix"""
        assert truncate_string(text, max_length) == expected

    @pytest.mark.parametrize("text,max_length,suffix,expected", [
        ("Long text here", 10, "...", "Long te..."),
        ("Another example", 10, "…", "Another e…"),
        ("Short suffix text", 12, " [more]", "Short [more]"),
        ("Custom", 5, ">>", "Cus>>"),
    ])
    def test_custom_suffix(self, text, max_length, suffix, expected):
        """Test truncation with custom suffix"""
        assert truncate_string(text, max_length, suffix) == expected

    def test_suffix_longer_than_max(self):
        """Test when suffix is longer than max_length"""
        result = truncate_string("text", 2, "...")
        assert result == ".."
        assert len(result) == 2

    def test_empty_string(self):
        """Test empty string returns empty"""
        assert truncate_string("", 10) == ""

    def test_max_length_zero(self):
        """Test max_length of 0"""
        result = truncate_string("test", 0, "...")
        assert result == ""
        assert len(result) == 0

    def test_exact_length_no_truncation(self):
        """Test text exactly at max_length is not truncated"""
        text = "exactly10!"
        assert truncate_string(text, 10) == text


class TestFormatPercentage:
    """Test percentage formatting"""

    @pytest.mark.parametrize("value,expected", [
        (0.0, "0.0%"),
        (0.5, "50.0%"),
        (1.0, "100.0%"),
        (0.123, "12.3%"),
        (0.999, "99.9%"),
    ])
    def test_percentage_formatting(self, value, expected):
        """Test percentage conversion with default precision"""
        assert format_percentage(value) == expected

    @pytest.mark.parametrize("value,precision,expected", [
        (0.5, 0, "50%"),
        (0.5, 2, "50.00%"),
        (0.12345, 3, "12.345%"),
        (0.87654, 2, "87.65%"),
    ])
    def test_precision_control(self, value, precision, expected):
        """Test precision parameter"""
        assert format_percentage(value, precision) == expected

    def test_zero_value(self):
        """Test zero value"""
        assert format_percentage(0) == "0.0%"

    def test_values_over_one(self):
        """Test values over 1.0 (over 100%)"""
        assert format_percentage(1.5) == "150.0%"
        assert format_percentage(2.0) == "200.0%"

    def test_negative_value(self):
        """Test negative values"""
        assert format_percentage(-0.1) == "-10.0%"

    def test_very_small_value(self):
        """Test very small values"""
        result = format_percentage(0.001, 2)
        assert result == "0.10%"

    def test_very_large_precision(self):
        """Test high precision"""
        result = format_percentage(0.123456789, 5)
        assert result == "12.34568%"
