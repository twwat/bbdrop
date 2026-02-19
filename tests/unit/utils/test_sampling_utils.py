#!/usr/bin/env python3
"""
Comprehensive test suite for sampling_utils.py
Testing image sampling logic and dimension calculations
"""

from PIL import Image
from src.utils.sampling_utils import (
    get_sample_indices,
    calculate_dimensions_with_outlier_exclusion
)


class TestGetSampleIndices:
    """Test sample index generation for image sampling"""

    def test_empty_files_list(self):
        """Test empty files list returns empty indices"""
        config = {'sampling_method': 0, 'sampling_fixed_count': 10}
        assert get_sample_indices([], config) == []

    def test_fixed_count_sampling(self):
        """Test fixed count sampling method"""
        files = [f"image{i}.jpg" for i in range(100)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 25,
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        assert len(indices) <= 25
        assert all(0 <= i < 100 for i in indices)

    def test_percentage_sampling(self):
        """Test percentage-based sampling"""
        files = [f"image{i}.jpg" for i in range(100)]
        config = {
            'sampling_method': 1,
            'sampling_percentage': 10,  # 10%
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        # Should get ~10 samples (10% of 100)
        assert 8 <= len(indices) <= 12

    def test_exclude_first_image(self):
        """Test excluding first image"""
        files = [f"image{i}.jpg" for i in range(10)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_first': True,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        assert 0 not in indices

    def test_exclude_last_image(self):
        """Test excluding last image"""
        files = [f"image{i}.jpg" for i in range(10)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_first': False,
            'exclude_last': True
        }
        indices = get_sample_indices(files, config)
        assert 9 not in indices

    def test_exclude_both_first_and_last(self):
        """Test excluding both first and last images"""
        files = [f"image{i}.jpg" for i in range(10)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_first': True,
            'exclude_last': True
        }
        indices = get_sample_indices(files, config)
        assert 0 not in indices
        assert 9 not in indices
        assert len(indices) > 0

    def test_exclude_first_single_file(self):
        """Test exclude_first with single file doesn't exclude it"""
        files = ["image.jpg"]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 1,
            'exclude_first': True,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        # Should still return something
        assert len(indices) > 0

    def test_pattern_exclusion(self):
        """Test excluding files by pattern"""
        files = ["image01.jpg", "cover.jpg", "image02.jpg", "thumbnail.jpg", "image03.jpg"]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_patterns': True,
            'exclude_patterns_text': 'cover.jpg,thumb*',
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        # cover.jpg (index 1) and thumbnail.jpg (index 3) should be excluded
        assert 1 not in indices
        assert 3 not in indices

    def test_pattern_case_insensitive(self):
        """Test pattern matching is case-insensitive"""
        files = ["IMAGE.JPG", "COVER.jpg", "photo.JPG"]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_patterns': True,
            'exclude_patterns_text': 'cover*',
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        assert 1 not in indices  # COVER.jpg excluded

    def test_wildcard_patterns(self):
        """Test wildcard patterns"""
        files = ["img_001.jpg", "img_002.jpg", "thumb_001.jpg", "thumb_002.jpg"]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_patterns': True,
            'exclude_patterns_text': 'thumb_*',
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        assert 2 not in indices
        assert 3 not in indices
        assert 0 in indices or 1 in indices

    def test_small_image_exclusion(self, tmp_path):
        """Test excluding small images by dimension"""
        # Create test images
        files = []
        for i, size in enumerate([(1000, 1000), (500, 500), (1000, 1000), (300, 300)]):
            filename = f"image{i}.jpg"
            img = Image.new('RGB', size, color='red')
            img.save(tmp_path / filename)
            files.append(filename)

        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_small_images': True,
            'exclude_small_threshold': 50,  # 50% of largest
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config, str(tmp_path))
        # Images at indices 1 (25%) and 3 (9%) should be excluded
        assert 1 not in indices
        assert 3 not in indices

    def test_all_excluded_returns_middle(self):
        """Test when all images excluded, returns middle image"""
        files = [f"image{i}.jpg" for i in range(5)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 0,
            'exclude_first': True,
            'exclude_last': True,
            'exclude_patterns': True,
            'exclude_patterns_text': '*',
        }
        indices = get_sample_indices(files, config)
        assert len(indices) == 1
        assert indices[0] == 2  # Middle of 5 items

    def test_sample_count_exceeds_available(self):
        """Test requesting more samples than available files"""
        files = [f"image{i}.jpg" for i in range(5)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 100,
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        assert len(indices) == 5

    def test_strategic_sampling_includes_endpoints(self):
        """Test strategic sampling includes first and last available"""
        files = [f"image{i}.jpg" for i in range(100)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 10,
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        # Should include first (0) and last (99) of available
        assert 0 in indices
        assert 99 in indices

    def test_even_distribution(self):
        """Test samples are evenly distributed"""
        files = [f"image{i}.jpg" for i in range(100)]
        config = {
            'sampling_method': 0,
            'sampling_fixed_count': 5,
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        # Check indices are sorted and spread
        sorted_indices = sorted(indices)
        assert sorted_indices == indices  # Should already be sorted
        # Check reasonable spacing
        if len(indices) > 1:
            gaps = [sorted_indices[i+1] - sorted_indices[i] for i in range(len(sorted_indices)-1)]
            # All gaps should be reasonably similar
            assert max(gaps) - min(gaps) < 30

    def test_percentage_with_small_list(self):
        """Test percentage sampling with small file list"""
        files = ["img1.jpg", "img2.jpg", "img3.jpg"]
        config = {
            'sampling_method': 1,
            'sampling_percentage': 10,  # 10% of 3 = 0.3
            'exclude_first': False,
            'exclude_last': False
        }
        indices = get_sample_indices(files, config)
        # Should return at least 1 sample
        assert len(indices) >= 1


class TestCalculateDimensionsWithOutlierExclusion:
    """Test dimension calculation with outlier handling"""

    def test_empty_dimensions(self):
        """Test empty dimensions list"""
        result = calculate_dimensions_with_outlier_exclusion([])
        assert result['avg_width'] == 0.0
        assert result['avg_height'] == 0.0
        assert result['min_width'] == 0.0
        assert result['max_width'] == 0.0

    def test_single_dimension(self):
        """Test single dimension"""
        dims = [(1920, 1080)]
        result = calculate_dimensions_with_outlier_exclusion(dims)
        assert result['avg_width'] == 1920.0
        assert result['avg_height'] == 1080.0
        assert result['min_width'] == 1920.0
        assert result['max_width'] == 1920.0

    def test_mean_calculation(self):
        """Test mean calculation without outlier exclusion"""
        dims = [(1000, 800), (2000, 1600), (1500, 1200)]
        result = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=False, use_median=False
        )
        assert result['avg_width'] == 1500.0  # (1000+2000+1500)/3
        assert result['avg_height'] == 1200.0  # (800+1600+1200)/3

    def test_median_calculation(self):
        """Test median calculation"""
        dims = [(1000, 800), (2000, 1600), (1500, 1200)]
        result = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=False, use_median=True
        )
        assert result['avg_width'] == 1500.0  # Median of [1000, 1500, 2000]
        assert result['avg_height'] == 1200.0  # Median of [800, 1200, 1600]

    def test_min_max_values(self):
        """Test min and max tracking"""
        dims = [(1920, 1080), (3840, 2160), (1280, 720)]
        result = calculate_dimensions_with_outlier_exclusion(dims)
        assert result['min_width'] == 1280.0
        assert result['max_width'] == 3840.0
        assert result['min_height'] == 720.0
        assert result['max_height'] == 2160.0

    def test_outlier_exclusion_with_outliers(self):
        """Test outlier exclusion removes extreme values"""
        # Create data with clear outliers
        dims = [
            (1000, 1000),
            (1000, 1000),
            (1000, 1000),
            (1000, 1000),
            (1000, 1000),
            (5000, 5000),  # Outlier
        ]
        result = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=True, use_median=False
        )
        # Average should be close to 1000, not affected by 5000
        assert result['avg_width'] < 1500.0
        assert result['avg_height'] < 1500.0

    def test_outlier_exclusion_insufficient_data(self):
        """Test outlier exclusion needs >4 samples"""
        dims = [(1000, 1000), (2000, 2000), (3000, 3000)]
        result_with = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=True, use_median=False
        )
        result_without = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=False, use_median=False
        )
        # With <5 samples, outlier exclusion shouldn't activate
        assert result_with['avg_width'] == result_without['avg_width']

    def test_iqr_outlier_removal(self):
        """Test IQR method for outlier removal"""
        # Create data with outliers: 9 normal values + 1 outlier
        dims = [(100, 100)] * 9 + [(1000, 1000)]
        result = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=True, use_median=False
        )
        # Should exclude the (1000, 1000) outlier
        assert result['avg_width'] < 200.0
        assert result['avg_height'] < 200.0

    def test_median_with_even_count(self):
        """Test median with even number of samples"""
        dims = [(1000, 1000), (2000, 2000), (3000, 3000), (4000, 4000)]
        result = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=False, use_median=True
        )
        # Median of [1000, 2000, 3000, 4000] should be element at index 2
        assert result['avg_width'] == 3000.0
        assert result['avg_height'] == 3000.0

    def test_median_with_odd_count(self):
        """Test median with odd number of samples"""
        dims = [(1000, 1000), (2000, 2000), (3000, 3000)]
        result = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=False, use_median=True
        )
        # Median is middle element
        assert result['avg_width'] == 2000.0
        assert result['avg_height'] == 2000.0

    def test_all_same_values(self):
        """Test with all identical dimensions"""
        dims = [(1920, 1080)] * 10
        result = calculate_dimensions_with_outlier_exclusion(dims)
        assert result['avg_width'] == 1920.0
        assert result['avg_height'] == 1080.0
        assert result['min_width'] == 1920.0
        assert result['max_width'] == 1920.0

    def test_mixed_aspect_ratios(self):
        """Test with mixed aspect ratios"""
        dims = [
            (1920, 1080),  # 16:9
            (1080, 1920),  # 9:16 (portrait)
            (1000, 1000),  # 1:1 (square)
        ]
        result = calculate_dimensions_with_outlier_exclusion(dims)
        assert result['avg_width'] == 1333.333333333333 or abs(result['avg_width'] - 1333.33) < 0.1
        assert result['avg_height'] == 1333.333333333333 or abs(result['avg_height'] - 1333.33) < 0.1

    def test_outlier_exclusion_with_median(self):
        """Test combining outlier exclusion with median"""
        dims = [(1000, 1000)] * 10 + [(5000, 5000)]
        result = calculate_dimensions_with_outlier_exclusion(
            dims, exclude_outliers=True, use_median=True
        )
        # Should exclude outlier and use median of remaining
        assert result['avg_width'] == 1000.0
        assert result['avg_height'] == 1000.0

    def test_return_type_float(self):
        """Test all returned values are floats"""
        dims = [(1920, 1080)]
        result = calculate_dimensions_with_outlier_exclusion(dims)
        for key, value in result.items():
            assert isinstance(value, float), f"{key} should be float, got {type(value)}"

    def test_large_dataset(self):
        """Test with large dataset"""
        # 1000 samples with slight variation
        dims = [(1920 + i % 10, 1080 + i % 10) for i in range(1000)]
        result = calculate_dimensions_with_outlier_exclusion(dims)
        # Should handle large dataset efficiently
        assert 1920.0 <= result['avg_width'] <= 1930.0
        assert 1080.0 <= result['avg_height'] <= 1090.0
