"""Tests for cover photo detection during gallery scanning."""
import os
import pytest
from unittest.mock import patch


class TestCoverDetector:
    """Cover detection from filename patterns."""

    def test_detect_cover_by_default_pattern(self):
        from src.core.cover_detector import detect_cover
        files = ["image001.jpg", "image002.jpg", "cover.jpg", "image003.jpg"]
        result = detect_cover(files, patterns="cover*")
        assert result == "cover.jpg"

    def test_detect_cover_multiple_patterns(self):
        from src.core.cover_detector import detect_cover
        files = ["image001.jpg", "poster.png", "image002.jpg"]
        result = detect_cover(files, patterns="cover*, poster*")
        assert result == "poster.png"

    def test_no_cover_found(self):
        from src.core.cover_detector import detect_cover
        files = ["image001.jpg", "image002.jpg"]
        result = detect_cover(files, patterns="cover*, poster*")
        assert result is None

    def test_first_match_wins(self):
        from src.core.cover_detector import detect_cover
        files = ["poster.jpg", "cover.jpg", "image001.jpg"]
        result = detect_cover(files, patterns="cover*, poster*")
        assert result == "cover.jpg"

    def test_case_insensitive_matching(self):
        from src.core.cover_detector import detect_cover
        files = ["COVER.JPG", "image001.jpg"]
        result = detect_cover(files, patterns="cover*")
        assert result == "COVER.JPG"

    def test_empty_patterns_returns_none(self):
        from src.core.cover_detector import detect_cover
        files = ["cover.jpg", "image001.jpg"]
        result = detect_cover(files, patterns="")
        assert result is None

    def test_suffix_pattern(self):
        from src.core.cover_detector import detect_cover
        files = ["image001.jpg", "gallery_cover.jpg", "image002.jpg"]
        result = detect_cover(files, patterns="*_cover.*")
        assert result == "gallery_cover.jpg"
