"""
Tests for TurboImageHostClient.sanitize_gallery_name().

Verifies gallery name sanitization: only letters, digits, spaces, hyphens,
and underscores are allowed. Max 20 chars. Empty/invalid names return 'untitled'.
"""

import pytest
from unittest.mock import patch

from src.network.turbo_image_host_client import TurboImageHostClient


@pytest.fixture
def turbo_client():
    """Build a TurboImageHostClient with __init__ bypassed."""
    with patch.object(TurboImageHostClient, '__init__', return_value=None):
        client = TurboImageHostClient()
        return client


class TestTurboSanitizeGalleryName:
    """Test TurboImageHostClient.sanitize_gallery_name()."""

    def test_dots_are_stripped(self, turbo_client):
        """Dots should be removed from gallery names."""
        assert turbo_client.sanitize_gallery_name("my.gallery") == "mygallery"

    def test_multiple_dots_stripped(self, turbo_client):
        """Multiple dots should all be removed."""
        assert turbo_client.sanitize_gallery_name("a.b.c.d") == "abcd"

    def test_special_chars_stripped(self, turbo_client):
        """All special characters should be stripped."""
        assert turbo_client.sanitize_gallery_name("test!@#$%name") == "testname"

    def test_allowed_chars_kept(self, turbo_client):
        """Letters, digits, hyphens, and underscores are preserved."""
        assert turbo_client.sanitize_gallery_name("good-name_here") == "good-name_here"

    def test_spaces_kept(self, turbo_client):
        """Spaces are allowed in gallery names."""
        assert turbo_client.sanitize_gallery_name("spaces are fine") == "spaces are fine"

    def test_brackets_stripped(self, turbo_client):
        """Parentheses and square brackets should be stripped."""
        assert turbo_client.sanitize_gallery_name("(brackets)[removed]") == "bracketsremoved"

    def test_truncation_at_20_chars(self, turbo_client):
        """Names longer than 20 characters should be truncated."""
        long_name = "a" * 30
        result = turbo_client.sanitize_gallery_name(long_name)
        assert len(result) == 20
        assert result == "a" * 20

    def test_empty_string_returns_untitled(self, turbo_client):
        """Empty string should return 'untitled'."""
        assert turbo_client.sanitize_gallery_name("") == "untitled"

    def test_none_returns_untitled(self, turbo_client):
        """None (falsy) should return 'untitled'."""
        assert turbo_client.sanitize_gallery_name(None) == "untitled"

    def test_all_invalid_chars_returns_untitled(self, turbo_client):
        """Name with only invalid chars should return 'untitled'."""
        assert turbo_client.sanitize_gallery_name("!@#$%^&*()") == "untitled"

    def test_whitespace_only_returns_untitled(self, turbo_client):
        """Whitespace-only name should return 'untitled' after strip."""
        assert turbo_client.sanitize_gallery_name("   ") == "untitled"

    def test_digits_preserved(self, turbo_client):
        """Digits should be preserved."""
        assert turbo_client.sanitize_gallery_name("gallery123") == "gallery123"

    def test_unicode_letters_preserved(self, turbo_client):
        r"""Unicode letters are matched by \w and should be preserved."""
        result = turbo_client.sanitize_gallery_name("galerie_été")
        assert "été" in result

    def test_leading_trailing_whitespace_stripped(self, turbo_client):
        """Leading and trailing whitespace should be stripped."""
        assert turbo_client.sanitize_gallery_name("  hello  ") == "hello"

    def test_truncation_after_sanitization(self, turbo_client):
        """Truncation should happen after special chars are removed."""
        # 25 valid chars after stripping the dots
        name = "a.b" * 10 + "ccccc"  # "a.ba.ba.ba.ba.ba.ba.ba.ba.ba.bccccc" -> "ababababababababababaccccc" (25 chars)
        result = turbo_client.sanitize_gallery_name(name)
        assert len(result) <= 20

    @pytest.mark.parametrize("input_name,expected", [
        ("simple", "simple"),
        ("with spaces", "with spaces"),
        ("with-hyphens", "with-hyphens"),
        ("under_scores", "under_scores"),
        ("MiXeD CaSe", "MiXeD CaSe"),
        ("file.name.ext", "filenameext"),
        ("path/to\\name", "pathtoname"),
        ("angle<brackets>", "anglebrackets"),
        ("pipe|char", "pipechar"),
        ("colon:semi;", "colonsemi"),
        ("quote'double\"", "quotedouble"),
    ])
    def test_parametrized_cases(self, turbo_client, input_name, expected):
        """Parametrized test for various input patterns."""
        assert turbo_client.sanitize_gallery_name(input_name) == expected
