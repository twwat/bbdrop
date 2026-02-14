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


class TestDetectCoversByFilename:
    """detect_covers_by_filename returns ALL matching filenames, not just first."""

    def test_returns_all_matches(self):
        from src.core.cover_detector import detect_covers_by_filename
        files = ["cover.jpg", "image001.jpg", "cover_back.jpg", "image002.jpg"]
        result = detect_covers_by_filename(files, patterns="cover*")
        assert result == ["cover.jpg", "cover_back.jpg"]

    def test_multiple_patterns_all_matches(self):
        from src.core.cover_detector import detect_covers_by_filename
        # Results preserve original file order, not pattern order
        files = ["cover.jpg", "poster.png", "image001.jpg", "cover_back.jpg"]
        result = detect_covers_by_filename(files, patterns="cover*, poster*")
        assert result == ["cover.jpg", "poster.png", "cover_back.jpg"]

    def test_no_matches_returns_empty_list(self):
        from src.core.cover_detector import detect_covers_by_filename
        files = ["image001.jpg", "image002.jpg"]
        result = detect_covers_by_filename(files, patterns="cover*")
        assert result == []

    def test_empty_patterns_returns_empty_list(self):
        from src.core.cover_detector import detect_covers_by_filename
        files = ["cover.jpg", "image001.jpg"]
        result = detect_covers_by_filename(files, patterns="")
        assert result == []

    def test_case_insensitive(self):
        from src.core.cover_detector import detect_covers_by_filename
        files = ["COVER.JPG", "Cover_Back.png", "image001.jpg"]
        result = detect_covers_by_filename(files, patterns="cover*")
        assert result == ["COVER.JPG", "Cover_Back.png"]

    def test_no_duplicates_across_patterns(self):
        from src.core.cover_detector import detect_covers_by_filename
        # "cover.jpg" matches both "cover*" and "*ver*" -- should appear only once
        files = ["cover.jpg", "image001.jpg"]
        result = detect_covers_by_filename(files, patterns="cover*, *ver*")
        assert result == ["cover.jpg"]

    def test_empty_filenames(self):
        from src.core.cover_detector import detect_covers_by_filename
        result = detect_covers_by_filename([], patterns="cover*")
        assert result == []

    def test_whitespace_only_patterns(self):
        from src.core.cover_detector import detect_covers_by_filename
        files = ["cover.jpg"]
        result = detect_covers_by_filename(files, patterns="  ,  , ")
        assert result == []


class TestDetectCoverByDimensions:
    """detect_cover_by_dimensions filters by area deviation and absolute bounds."""

    def test_differs_from_average_area(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # Average area of all = (100*100 + 100*100 + 200*200) / 3 = (10000+10000+40000)/3 = 20000
        # big.jpg area=40000, deviation = |40000-20000|/20000 = 100% > 50%
        dims = {
            "img1.jpg": (100, 100),
            "img2.jpg": (100, 100),
            "big.jpg": (200, 200),
        }
        result = detect_cover_by_dimensions(dims, differs_percent=50)
        assert result == ["big.jpg"]

    def test_differs_percent_zero_matches_nothing(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # 0% means area must differ by more than 0% -- only exact average passes
        # All images same size: each area = average, deviation = 0%, not > 0%
        dims = {
            "img1.jpg": (100, 100),
            "img2.jpg": (100, 100),
        }
        result = detect_cover_by_dimensions(dims, differs_percent=0)
        assert result == []

    def test_min_shortest_side_filter(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # small: shortest side = 100, wide: shortest side = 200
        dims = {
            "small.jpg": (100, 200),
            "wide.jpg": (500, 200),
        }
        result = detect_cover_by_dimensions(dims, min_shortest_side=200)
        assert result == ["wide.jpg"]

    def test_min_shortest_side_portrait(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # Portrait image: shortest side is width
        dims = {
            "narrow.jpg": (150, 500),
            "square.jpg": (300, 300),
        }
        result = detect_cover_by_dimensions(dims, min_shortest_side=200)
        assert result == ["square.jpg"]

    def test_max_longest_side_filter(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # small: longest side = 200, wide: longest side = 500
        dims = {
            "small.jpg": (100, 200),
            "wide.jpg": (500, 200),
        }
        result = detect_cover_by_dimensions(dims, max_longest_side=300)
        assert result == ["small.jpg"]

    def test_max_longest_side_portrait(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # Portrait image: longest side is height
        dims = {
            "tall.jpg": (200, 600),
            "compact.jpg": (200, 250),
        }
        result = detect_cover_by_dimensions(dims, max_longest_side=300)
        assert result == ["compact.jpg"]

    def test_all_criteria_combined_as_and(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # Only "big.jpg" should pass ALL criteria:
        # - differs from average by > 30%
        # - min_shortest_side=150, max_longest_side=300
        dims = {
            "small.jpg": (100, 100),   # area 10000, shortest=100, longest=100
            "medium.jpg": (150, 150),  # area 22500, shortest=150, longest=150
            "big.jpg": (250, 250),     # area 62500, shortest=250, longest=250
        }
        # avg area = (10000+22500+62500)/3 = 31666.67
        # small: deviation 68.4% > 30% -- but shortest=100 < 150, fails min
        # medium: deviation 28.9% -- not > 30%, fails differs
        # big: deviation 97.4% > 30%, shortest=250>=150, longest=250<=300 -- passes
        result = detect_cover_by_dimensions(
            dims,
            differs_percent=30,
            min_shortest_side=150,
            max_longest_side=300,
        )
        assert result == ["big.jpg"]

    def test_no_criteria_returns_empty(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        dims = {"img1.jpg": (100, 100)}
        # No criteria specified -- nothing can match
        result = detect_cover_by_dimensions(dims)
        assert result == []

    def test_empty_input(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        result = detect_cover_by_dimensions({}, differs_percent=50)
        assert result == []

    def test_single_image_differs_percent(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # Single image: its area IS the average, deviation = 0%, never > X%
        dims = {"only.jpg": (200, 200)}
        result = detect_cover_by_dimensions(dims, differs_percent=10)
        assert result == []

    def test_smaller_image_also_detected_by_differs(self):
        from src.core.cover_detector import detect_cover_by_dimensions
        # Both outliers (small and big) should be detected
        dims = {
            "tiny.jpg": (50, 50),     # area 2500
            "normal1.jpg": (200, 200), # area 40000
            "normal2.jpg": (200, 200), # area 40000
            "huge.jpg": (400, 400),    # area 160000
        }
        # avg = (2500+40000+40000+160000)/4 = 60625
        # tiny: |2500-60625|/60625 = 95.9% > 50%
        # normal1: |40000-60625|/60625 = 34.0% -- not > 50%
        # normal2: same as normal1
        # huge: |160000-60625|/60625 = 163.9% > 50%
        result = detect_cover_by_dimensions(dims, differs_percent=50)
        assert "tiny.jpg" in result
        assert "huge.jpg" in result
        assert len(result) == 2


class TestDetectCoverByFileSize:
    """detect_cover_by_file_size filters by min/max KB range."""

    def test_min_kb_filter(self):
        from src.core.cover_detector import detect_cover_by_file_size
        sizes = {
            "small.jpg": 50 * 1024,    # 50 KB
            "big.jpg": 500 * 1024,     # 500 KB
        }
        result = detect_cover_by_file_size(sizes, min_kb=100)
        assert result == ["big.jpg"]

    def test_max_kb_filter(self):
        from src.core.cover_detector import detect_cover_by_file_size
        sizes = {
            "small.jpg": 50 * 1024,    # 50 KB
            "big.jpg": 500 * 1024,     # 500 KB
        }
        result = detect_cover_by_file_size(sizes, max_kb=100)
        assert result == ["small.jpg"]

    def test_range_filter(self):
        from src.core.cover_detector import detect_cover_by_file_size
        sizes = {
            "tiny.jpg": 10 * 1024,      # 10 KB
            "medium.jpg": 150 * 1024,   # 150 KB
            "huge.jpg": 2000 * 1024,    # 2000 KB
        }
        result = detect_cover_by_file_size(sizes, min_kb=100, max_kb=500)
        assert result == ["medium.jpg"]

    def test_no_criteria_returns_empty(self):
        from src.core.cover_detector import detect_cover_by_file_size
        sizes = {"img.jpg": 100 * 1024}
        result = detect_cover_by_file_size(sizes)
        assert result == []

    def test_empty_input(self):
        from src.core.cover_detector import detect_cover_by_file_size
        result = detect_cover_by_file_size({}, min_kb=100)
        assert result == []

    def test_boundary_exact_min(self):
        from src.core.cover_detector import detect_cover_by_file_size
        # Exactly at min_kb boundary -- should be included (>=)
        sizes = {"exact.jpg": 100 * 1024}
        result = detect_cover_by_file_size(sizes, min_kb=100)
        assert result == ["exact.jpg"]

    def test_boundary_exact_max(self):
        from src.core.cover_detector import detect_cover_by_file_size
        # Exactly at max_kb boundary -- should be included (<=)
        sizes = {"exact.jpg": 100 * 1024}
        result = detect_cover_by_file_size(sizes, max_kb=100)
        assert result == ["exact.jpg"]

    def test_zero_size_file(self):
        from src.core.cover_detector import detect_cover_by_file_size
        sizes = {"empty.jpg": 0, "normal.jpg": 50 * 1024}
        result = detect_cover_by_file_size(sizes, max_kb=1)
        assert result == ["empty.jpg"]


class TestDeduplicateCovers:
    """deduplicate_covers removes entries with same file size, keeping first."""

    def test_removes_same_size_duplicates(self):
        from src.core.cover_detector import deduplicate_covers
        candidates = ["cover.jpg", "cover_copy.jpg", "poster.jpg"]
        file_sizes = {
            "cover.jpg": 102400,
            "cover_copy.jpg": 102400,  # same size as cover.jpg
            "poster.jpg": 204800,
        }
        result = deduplicate_covers(candidates, file_sizes)
        assert result == ["cover.jpg", "poster.jpg"]

    def test_no_duplicates(self):
        from src.core.cover_detector import deduplicate_covers
        candidates = ["a.jpg", "b.jpg", "c.jpg"]
        file_sizes = {"a.jpg": 100, "b.jpg": 200, "c.jpg": 300}
        result = deduplicate_covers(candidates, file_sizes)
        assert result == ["a.jpg", "b.jpg", "c.jpg"]

    def test_empty_candidates(self):
        from src.core.cover_detector import deduplicate_covers
        result = deduplicate_covers([], {})
        assert result == []

    def test_preserves_order(self):
        from src.core.cover_detector import deduplicate_covers
        candidates = ["z.jpg", "a.jpg", "m.jpg"]
        file_sizes = {"z.jpg": 300, "a.jpg": 100, "m.jpg": 200}
        result = deduplicate_covers(candidates, file_sizes)
        assert result == ["z.jpg", "a.jpg", "m.jpg"]

    def test_three_same_size_keeps_first(self):
        from src.core.cover_detector import deduplicate_covers
        candidates = ["first.jpg", "second.jpg", "third.jpg"]
        file_sizes = {"first.jpg": 100, "second.jpg": 100, "third.jpg": 100}
        result = deduplicate_covers(candidates, file_sizes)
        assert result == ["first.jpg"]

    def test_missing_file_size_kept(self):
        from src.core.cover_detector import deduplicate_covers
        # If a candidate has no entry in file_sizes, it should still be kept
        candidates = ["known.jpg", "unknown.jpg"]
        file_sizes = {"known.jpg": 100}
        result = deduplicate_covers(candidates, file_sizes)
        assert result == ["known.jpg", "unknown.jpg"]


class TestApplyMaxCovers:
    """apply_max_covers limits list length. 0 = unlimited."""

    def test_limits_to_max(self):
        from src.core.cover_detector import apply_max_covers
        candidates = ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
        result = apply_max_covers(candidates, max_covers=2)
        assert result == ["a.jpg", "b.jpg"]

    def test_zero_means_unlimited(self):
        from src.core.cover_detector import apply_max_covers
        candidates = ["a.jpg", "b.jpg", "c.jpg"]
        result = apply_max_covers(candidates, max_covers=0)
        assert result == ["a.jpg", "b.jpg", "c.jpg"]

    def test_max_larger_than_list(self):
        from src.core.cover_detector import apply_max_covers
        candidates = ["a.jpg", "b.jpg"]
        result = apply_max_covers(candidates, max_covers=10)
        assert result == ["a.jpg", "b.jpg"]

    def test_max_one(self):
        from src.core.cover_detector import apply_max_covers
        candidates = ["a.jpg", "b.jpg", "c.jpg"]
        result = apply_max_covers(candidates, max_covers=1)
        assert result == ["a.jpg"]

    def test_empty_list(self):
        from src.core.cover_detector import apply_max_covers
        result = apply_max_covers([], max_covers=5)
        assert result == []

    def test_does_not_mutate_original(self):
        from src.core.cover_detector import apply_max_covers
        candidates = ["a.jpg", "b.jpg", "c.jpg"]
        original = candidates.copy()
        apply_max_covers(candidates, max_covers=1)
        assert candidates == original
