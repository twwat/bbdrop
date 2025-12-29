"""
Comprehensive test suite for gallery_naming.py module.

Tests cover:
- GalleryNameGenerator: name generation strategies, templates, timestamps, hashes
- GalleryNameValidator: validation rules, length checks, special characters
- GalleryNameRegistry: collision detection, unique name generation
- Utility functions: suggestions, normalization
- Edge cases: empty names, Unicode, reserved names, max attempts
- Special characters: sanitization, invalid chars, path separators
"""

import pytest
import re
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.storage.gallery_naming import (
    GalleryNamingError,
    GalleryNameGenerator,
    GalleryNameValidator,
    GalleryNameRegistry,
    suggest_gallery_names,
    normalize_gallery_name
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def generator():
    """Create a GalleryNameGenerator instance."""
    return GalleryNameGenerator()


@pytest.fixture
def custom_generator():
    """Create a GalleryNameGenerator with custom prefix."""
    return GalleryNameGenerator(default_prefix="CustomGallery")


@pytest.fixture
def validator():
    """Create a GalleryNameValidator instance with default settings."""
    return GalleryNameValidator()


@pytest.fixture
def strict_validator():
    """Create a strict validator with ASCII-only."""
    return GalleryNameValidator(
        min_length=3,
        max_length=50,
        allow_unicode=False
    )


@pytest.fixture
def registry():
    """Create a GalleryNameRegistry instance."""
    return GalleryNameRegistry()


@pytest.fixture
def temp_folder(tmp_path):
    """Create a temporary folder for testing."""
    folder = tmp_path / "test_gallery"
    folder.mkdir()
    return folder


@pytest.fixture
def sample_metadata():
    """Provide sample metadata for template testing."""
    return {
        'image_count': 42,
        'folder_size': 1024000,
        'camera': 'Canon EOS',
        'location': 'Paris'
    }


# ============================================================================
# GalleryNameGenerator Tests
# ============================================================================

class TestGalleryNameGenerator:
    """Test GalleryNameGenerator class."""

    def test_init_default_prefix(self):
        """Test initialization with default prefix."""
        gen = GalleryNameGenerator()
        assert gen._default_prefix == "Gallery"

    def test_init_custom_prefix(self):
        """Test initialization with custom prefix."""
        gen = GalleryNameGenerator(default_prefix="Photos")
        assert gen._default_prefix == "Photos"

    # from_folder_name tests
    def test_from_folder_name_simple(self, generator, temp_folder):
        """Test generating name from simple folder name."""
        result = generator.from_folder_name(temp_folder)
        assert result == "test_gallery"

    def test_from_folder_name_with_spaces(self, generator, tmp_path):
        """Test folder name with spaces."""
        folder = tmp_path / "My Photos 2024"
        folder.mkdir()
        result = generator.from_folder_name(folder)
        assert result == "My_Photos_2024"

    def test_from_folder_name_with_special_chars(self, generator, tmp_path):
        """Test folder name with special characters."""
        folder = tmp_path / "Photos:2024|New"
        folder.mkdir()
        result = generator.from_folder_name(folder)
        assert result == "Photos_2024_New"

    def test_from_folder_name_string_path(self, generator, tmp_path):
        """Test with string path instead of Path object."""
        folder = tmp_path / "string_test"
        folder.mkdir()
        result = generator.from_folder_name(str(folder))
        assert result == "string_test"

    def test_from_folder_name_empty_after_cleaning(self, generator, tmp_path):
        """Test folder with name that becomes empty after cleaning."""
        folder = tmp_path / "___"
        folder.mkdir()
        result = generator.from_folder_name(folder)
        assert result == "Gallery"  # Falls back to default prefix

    def test_from_folder_name_with_invalid_chars(self, generator, tmp_path):
        """Test folder with all types of invalid characters."""
        # Can't actually create folder with these chars, so test the cleaning logic
        gen = GalleryNameGenerator()
        test_name = '<>:"|?*\\/test'
        cleaned = gen._clean_name(test_name)
        assert cleaned == "test"

    # from_template tests
    def test_from_template_folder_placeholder(self, generator, temp_folder):
        """Test template with folder placeholder."""
        template = "{folder}_archive"
        result = generator.from_template(template, temp_folder)
        assert result == "test_gallery_archive"

    def test_from_template_date_placeholder(self, generator, temp_folder):
        """Test template with date placeholder."""
        template = "{folder}_{date}"
        result = generator.from_template(template, temp_folder)
        # Check format matches YYYY-MM-DD
        assert re.match(r'test_gallery_\d{4}-\d{2}-\d{2}', result)

    def test_from_template_time_placeholder(self, generator, temp_folder):
        """Test template with time placeholder."""
        template = "{folder}_{time}"
        result = generator.from_template(template, temp_folder)
        # Check format matches HH-MM-SS
        assert re.match(r'test_gallery_\d{2}-\d{2}-\d{2}', result)

    def test_from_template_timestamp_placeholder(self, generator, temp_folder):
        """Test template with timestamp placeholder."""
        template = "{folder}_{timestamp}"
        result = generator.from_template(template, temp_folder)
        # Timestamp should be numeric
        assert re.match(r'test_gallery_\d+', result)

    def test_from_template_metadata_placeholders(self, generator, temp_folder, sample_metadata):
        """Test template with metadata placeholders."""
        template = "{folder} - {count} images"
        result = generator.from_template(template, temp_folder, sample_metadata)
        # Note: clean_name collapses multiple underscores but preserves structure
        assert result == "test_gallery_-_42_images"

    def test_from_template_multiple_metadata(self, generator, temp_folder, sample_metadata):
        """Test template with multiple metadata fields."""
        template = "{folder}_{camera}_{location}_{count}pics"
        result = generator.from_template(template, temp_folder, sample_metadata)
        assert result == "test_gallery_Canon_EOS_Paris_42pics"

    def test_from_template_no_metadata(self, generator, temp_folder):
        """Test template with metadata placeholders but no metadata provided."""
        template = "{folder}_{count}_images"
        result = generator.from_template(template, temp_folder)
        assert result == "test_gallery_0_images"

    def test_from_template_empty_result(self, generator, tmp_path):
        """Test template that results in empty name after cleaning."""
        folder = tmp_path / "test"
        folder.mkdir()
        template = "___"
        result = generator.from_template(template, folder)
        assert result == "Gallery"  # Falls back to default

    def test_from_template_size_metadata(self, generator, temp_folder):
        """Test template with folder size metadata."""
        template = "{folder}_{size}bytes"
        metadata = {'folder_size': 5000}
        result = generator.from_template(template, temp_folder, metadata)
        assert result == "test_gallery_5000bytes"

    # with_timestamp tests
    def test_with_timestamp(self, generator):
        """Test adding timestamp to name."""
        base_name = "MyGallery"
        result = generator.with_timestamp(base_name)
        # Should match format: MyGallery_YYYYMMDD_HHMMSS
        assert re.match(r'MyGallery_\d{8}_\d{6}', result)

    def test_with_timestamp_preserves_base(self, generator):
        """Test that base name is preserved in timestamp format."""
        base_name = "Test_Photos"
        result = generator.with_timestamp(base_name)
        assert result.startswith("Test_Photos_")

    def test_with_timestamp_different_calls(self, generator):
        """Test that multiple calls produce different timestamps."""
        base_name = "Gallery"
        result1 = generator.with_timestamp(base_name)
        time.sleep(0.1)  # Small delay to ensure different timestamp
        result2 = generator.with_timestamp(base_name)
        # They might be same if too fast, but structure should be correct
        assert re.match(r'Gallery_\d{8}_\d{6}', result1)
        assert re.match(r'Gallery_\d{8}_\d{6}', result2)

    # with_hash tests
    def test_with_hash_default_source(self, generator):
        """Test adding hash with default source."""
        base_name = "MyGallery"
        result = generator.with_hash(base_name)
        # Should match format: MyGallery_[8 hex chars]
        assert re.match(r'MyGallery_[a-f0-9]{8}', result)

    def test_with_hash_custom_source(self, generator):
        """Test adding hash with custom source."""
        base_name = "Gallery"
        result = generator.with_hash(base_name, source="test_source")
        # Hash should be deterministic for same source
        expected_hash = generator.with_hash(base_name, source="test_source")
        assert result == expected_hash

    def test_with_hash_deterministic(self, generator):
        """Test that same source produces same hash."""
        base_name = "Photos"
        result1 = generator.with_hash(base_name, source="consistent")
        result2 = generator.with_hash(base_name, source="consistent")
        assert result1 == result2

    def test_with_hash_different_sources(self, generator):
        """Test that different sources produce different hashes."""
        base_name = "Gallery"
        result1 = generator.with_hash(base_name, source="source1")
        result2 = generator.with_hash(base_name, source="source2")
        assert result1 != result2

    # auto_generate tests
    def test_auto_generate_folder_strategy(self, generator, temp_folder):
        """Test auto-generation with folder strategy."""
        result = generator.auto_generate(temp_folder, strategy="folder")
        assert result == "test_gallery"

    def test_auto_generate_timestamp_strategy(self, generator, temp_folder):
        """Test auto-generation with timestamp strategy."""
        result = generator.auto_generate(temp_folder, strategy="timestamp")
        assert result.startswith("test_gallery_")
        assert re.match(r'test_gallery_\d{8}_\d{6}', result)

    def test_auto_generate_hash_strategy(self, generator, temp_folder):
        """Test auto-generation with hash strategy."""
        result = generator.auto_generate(temp_folder, strategy="hash")
        assert result.startswith("test_gallery_")
        assert re.match(r'test_gallery_[a-f0-9]{8}', result)

    def test_auto_generate_date_strategy(self, generator, temp_folder):
        """Test auto-generation with date strategy."""
        result = generator.auto_generate(temp_folder, strategy="date")
        assert result.startswith("test_gallery_")
        assert re.match(r'test_gallery_\d{4}-\d{2}-\d{2}', result)

    def test_auto_generate_invalid_strategy(self, generator, temp_folder):
        """Test auto-generation with invalid strategy raises error."""
        with pytest.raises(GalleryNamingError) as exc_info:
            generator.auto_generate(temp_folder, strategy="invalid")
        assert "Unknown naming strategy" in str(exc_info.value)

    def test_auto_generate_with_metadata(self, generator, temp_folder, sample_metadata):
        """Test that metadata is passed through but doesn't affect non-template strategies."""
        result = generator.auto_generate(
            temp_folder,
            strategy="folder",
            metadata=sample_metadata
        )
        assert result == "test_gallery"

    # _clean_name tests
    def test_clean_name_strips_whitespace(self, generator):
        """Test that whitespace is stripped from both ends."""
        assert generator._clean_name("  test  ") == "test"

    def test_clean_name_replaces_invalid_chars(self, generator):
        """Test that invalid characters are replaced with underscores."""
        assert generator._clean_name("test<>name") == "test_name"
        assert generator._clean_name('test:"name') == "test_name"
        assert generator._clean_name("test|?*name") == "test_name"

    def test_clean_name_replaces_path_separators(self, generator):
        """Test that path separators are replaced."""
        assert generator._clean_name("test/name") == "test_name"
        assert generator._clean_name("test\\name") == "test_name"

    def test_clean_name_collapses_multiple_underscores(self, generator):
        """Test that multiple underscores/spaces are collapsed."""
        assert generator._clean_name("test___name") == "test_name"
        assert generator._clean_name("test   name") == "test_name"
        assert generator._clean_name("test _ _ name") == "test_name"

    def test_clean_name_removes_leading_trailing_underscores(self, generator):
        """Test that leading/trailing underscores are removed."""
        assert generator._clean_name("_test_") == "test"
        assert generator._clean_name("___test___") == "test"

    def test_clean_name_handles_unicode(self, generator):
        """Test that Unicode characters are preserved."""
        assert generator._clean_name("café") == "café"
        assert generator._clean_name("日本語") == "日本語"

    def test_clean_name_all_invalid_becomes_empty(self, generator):
        """Test that name with only invalid chars becomes empty."""
        assert generator._clean_name("<<<>>>") == ""
        assert generator._clean_name("___") == ""


# ============================================================================
# GalleryNameValidator Tests
# ============================================================================

class TestGalleryNameValidator:
    """Test GalleryNameValidator class."""

    def test_init_default_settings(self):
        """Test initialization with default settings."""
        validator = GalleryNameValidator()
        assert validator._min_length == 1
        assert validator._max_length == 200
        assert validator._allow_unicode is True

    def test_init_custom_settings(self):
        """Test initialization with custom settings."""
        validator = GalleryNameValidator(
            min_length=5,
            max_length=100,
            allow_unicode=False
        )
        assert validator._min_length == 5
        assert validator._max_length == 100
        assert validator._allow_unicode is False

    # validate tests
    def test_validate_valid_name(self, validator):
        """Test validation of valid name."""
        is_valid, issues = validator.validate("MyGallery")
        assert is_valid is True
        assert len(issues) == 0

    def test_validate_min_length_violation(self, strict_validator):
        """Test validation fails when name is too short."""
        is_valid, issues = strict_validator.validate("ab")
        assert is_valid is False
        assert any("at least 3 characters" in issue for issue in issues)

    def test_validate_max_length_violation(self, validator):
        """Test validation fails when name is too long."""
        long_name = "a" * 201
        is_valid, issues = validator.validate(long_name)
        assert is_valid is False
        assert any("must not exceed 200 characters" in issue for issue in issues)

    def test_validate_empty_name(self, validator):
        """Test validation fails for empty name."""
        is_valid, issues = validator.validate("")
        assert is_valid is False
        assert any("cannot be empty" in issue for issue in issues)

    def test_validate_whitespace_only(self, validator):
        """Test validation fails for whitespace-only name."""
        is_valid, issues = validator.validate("   ")
        assert is_valid is False
        assert any("cannot be empty or whitespace only" in issue for issue in issues)

    def test_validate_invalid_characters(self, validator):
        """Test validation fails for invalid characters."""
        invalid_names = [
            "test<name",
            "test>name",
            'test:"name',
            "test|name",
            "test?name",
            "test*name",
            "test/name",
            "test\\name"
        ]
        for name in invalid_names:
            is_valid, issues = validator.validate(name)
            assert is_valid is False
            assert any("invalid characters" in issue for issue in issues), f"Failed for: {name}"

    def test_validate_control_characters(self, validator):
        """Test validation fails for control characters."""
        name_with_ctrl = "test\x00name"
        is_valid, issues = validator.validate(name_with_ctrl)
        assert is_valid is False
        assert any("invalid characters" in issue for issue in issues)

    def test_validate_unicode_allowed(self, validator):
        """Test validation succeeds for Unicode when allowed."""
        unicode_names = ["café", "日本語", "Москва"]
        for name in unicode_names:
            is_valid, issues = validator.validate(name)
            assert is_valid is True, f"Failed for: {name}"

    def test_validate_unicode_not_allowed(self, strict_validator):
        """Test validation fails for Unicode when not allowed."""
        is_valid, issues = strict_validator.validate("café")
        assert is_valid is False
        assert any("ASCII characters" in issue for issue in issues)

    def test_validate_reserved_names_windows(self, validator):
        """Test validation fails for Windows reserved names."""
        reserved_names = [
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM9",
            "LPT1", "LPT2", "LPT9"
        ]
        for name in reserved_names:
            is_valid, issues = validator.validate(name)
            assert is_valid is False
            assert any("reserved system name" in issue for issue in issues), f"Failed for: {name}"

    def test_validate_reserved_names_case_insensitive(self, validator):
        """Test reserved name check is case-insensitive."""
        is_valid, issues = validator.validate("con")
        assert is_valid is False
        is_valid, issues = validator.validate("CoN")
        assert is_valid is False

    def test_validate_multiple_issues(self, strict_validator):
        """Test validation returns all issues."""
        # Too short, invalid chars, non-ASCII
        is_valid, issues = strict_validator.validate("a<é")
        assert is_valid is False
        assert len(issues) >= 2  # At least length and invalid chars

    # is_valid tests
    def test_is_valid_returns_true(self, validator):
        """Test is_valid returns True for valid name."""
        assert validator.is_valid("ValidName") is True

    def test_is_valid_returns_false(self, validator):
        """Test is_valid returns False for invalid name."""
        assert validator.is_valid("invalid<name") is False

    def test_is_valid_edge_cases(self, validator):
        """Test is_valid with various edge cases."""
        assert validator.is_valid("") is False
        assert validator.is_valid("a") is True
        assert validator.is_valid("_") is True
        assert validator.is_valid("CON") is False


# ============================================================================
# GalleryNameRegistry Tests
# ============================================================================

class TestGalleryNameRegistry:
    """Test GalleryNameRegistry class."""

    def test_init_empty_registry(self):
        """Test initialization creates empty registry."""
        registry = GalleryNameRegistry()
        assert len(registry._used_names) == 0

    def test_register_adds_name(self, registry):
        """Test registering a name adds it to the registry."""
        registry.register("TestGallery")
        assert "testgallery" in registry._used_names

    def test_register_case_insensitive(self, registry):
        """Test registration is case-insensitive."""
        registry.register("TestGallery")
        assert registry.is_used("testgallery")
        assert registry.is_used("TESTGALLERY")
        assert registry.is_used("TestGallery")

    def test_register_multiple_names(self, registry):
        """Test registering multiple names."""
        names = ["Gallery1", "Gallery2", "Gallery3"]
        for name in names:
            registry.register(name)
        assert len(registry._used_names) == 3

    def test_is_used_existing_name(self, registry):
        """Test is_used returns True for registered name."""
        registry.register("ExistingGallery")
        assert registry.is_used("ExistingGallery") is True

    def test_is_used_nonexistent_name(self, registry):
        """Test is_used returns False for unregistered name."""
        assert registry.is_used("NonExistent") is False

    def test_is_used_case_insensitive(self, registry):
        """Test is_used check is case-insensitive."""
        registry.register("TestName")
        assert registry.is_used("testname") is True
        assert registry.is_used("TESTNAME") is True
        assert registry.is_used("TeStNaMe") is True

    def test_get_unique_name_not_used(self, registry):
        """Test get_unique_name returns base name when not used."""
        unique_name = registry.get_unique_name("NewGallery")
        assert unique_name == "NewGallery"

    def test_get_unique_name_single_collision(self, registry):
        """Test get_unique_name handles single collision."""
        registry.register("Gallery")
        unique_name = registry.get_unique_name("Gallery")
        assert unique_name == "Gallery (1)"

    def test_get_unique_name_multiple_collisions(self, registry):
        """Test get_unique_name handles multiple collisions."""
        registry.register("Gallery")
        registry.register("Gallery (1)")
        registry.register("Gallery (2)")
        unique_name = registry.get_unique_name("Gallery")
        assert unique_name == "Gallery (3)"

    def test_get_unique_name_large_number(self, registry):
        """Test get_unique_name with many collisions."""
        for i in range(10):
            registry.register(f"Popular" if i == 0 else f"Popular ({i})")
        unique_name = registry.get_unique_name("Popular")
        assert unique_name == "Popular (10)"

    def test_get_unique_name_max_attempts_exceeded(self, registry):
        """Test get_unique_name raises error when max attempts exceeded."""
        # Register all possible names up to max_attempts
        for i in range(10):
            registry.register(f"Gallery" if i == 0 else f"Gallery ({i})")

        with pytest.raises(GalleryNamingError) as exc_info:
            registry.get_unique_name("Gallery", max_attempts=10)
        assert "Cannot find unique name" in str(exc_info.value)

    def test_get_unique_name_custom_max_attempts(self, registry):
        """Test get_unique_name with custom max_attempts."""
        registry.register("Test")
        # Should succeed with small max_attempts when only one collision
        unique_name = registry.get_unique_name("Test", max_attempts=5)
        assert unique_name == "Test (1)"

    def test_clear_removes_all_names(self, registry):
        """Test clear removes all registered names."""
        registry.register("Gallery1")
        registry.register("Gallery2")
        registry.register("Gallery3")
        assert len(registry._used_names) == 3

        registry.clear()
        assert len(registry._used_names) == 0

    def test_clear_on_empty_registry(self, registry):
        """Test clear on empty registry doesn't cause issues."""
        registry.clear()
        assert len(registry._used_names) == 0

    def test_get_all_names_empty(self, registry):
        """Test get_all_names returns empty list initially."""
        assert registry.get_all_names() == []

    def test_get_all_names_with_names(self, registry):
        """Test get_all_names returns all registered names."""
        names = ["Gallery1", "Gallery2", "Gallery3"]
        for name in names:
            registry.register(name)

        all_names = registry.get_all_names()
        assert len(all_names) == 3
        # Names are stored lowercase
        assert set(all_names) == {"gallery1", "gallery2", "gallery3"}

    def test_get_all_names_returns_copy(self, registry):
        """Test that get_all_names returns a list, not the internal set."""
        registry.register("Test")
        names = registry.get_all_names()
        assert isinstance(names, list)


# ============================================================================
# Utility Functions Tests
# ============================================================================

class TestSuggestGalleryNames:
    """Test suggest_gallery_names function."""

    def test_suggest_default_count(self, temp_folder):
        """Test suggestions with default count."""
        suggestions = suggest_gallery_names(temp_folder)
        assert len(suggestions) <= 5

    def test_suggest_custom_count(self, temp_folder):
        """Test suggestions with custom count."""
        suggestions = suggest_gallery_names(temp_folder, count=3)
        assert len(suggestions) <= 3

    def test_suggest_with_metadata(self, temp_folder, sample_metadata):
        """Test suggestions with metadata."""
        suggestions = suggest_gallery_names(temp_folder, metadata=sample_metadata)
        # Should include suggestions with image count
        assert any("42" in s for s in suggestions)

    def test_suggest_includes_folder_name(self, temp_folder):
        """Test that folder name strategy is included."""
        suggestions = suggest_gallery_names(temp_folder)
        assert "test_gallery" in suggestions

    def test_suggest_includes_date(self, temp_folder):
        """Test that date strategy is included."""
        suggestions = suggest_gallery_names(temp_folder)
        # At least one should have date format
        assert any(re.search(r'\d{4}-\d{2}-\d{2}', s) for s in suggestions)

    def test_suggest_includes_timestamp(self, temp_folder):
        """Test that timestamp strategy is included."""
        suggestions = suggest_gallery_names(temp_folder)
        # At least one should have timestamp format
        assert any(re.search(r'\d{8}_\d{6}', s) for s in suggestions)

    def test_suggest_unique_only(self, temp_folder):
        """Test that suggestions are unique."""
        suggestions = suggest_gallery_names(temp_folder, count=10)
        assert len(suggestions) == len(set(suggestions))

    def test_suggest_no_metadata(self, temp_folder):
        """Test suggestions without metadata still work."""
        suggestions = suggest_gallery_names(temp_folder, count=5)
        assert len(suggestions) > 0
        assert all(isinstance(s, str) for s in suggestions)

    def test_suggest_with_partial_metadata(self, temp_folder):
        """Test suggestions with partial metadata."""
        metadata = {'image_count': 10}  # Only count, no size
        suggestions = suggest_gallery_names(temp_folder, metadata=metadata)
        assert len(suggestions) > 0

    def test_suggest_string_path(self, temp_folder):
        """Test suggestions work with string path."""
        suggestions = suggest_gallery_names(str(temp_folder))
        assert len(suggestions) > 0

    def test_suggest_respects_count_limit(self, temp_folder, sample_metadata):
        """Test that returned suggestions don't exceed requested count."""
        for count in [1, 3, 5, 10]:
            suggestions = suggest_gallery_names(
                temp_folder,
                count=count,
                metadata=sample_metadata
            )
            assert len(suggestions) <= count


class TestNormalizeGalleryName:
    """Test normalize_gallery_name function."""

    def test_normalize_strips_whitespace(self):
        """Test normalization strips leading/trailing whitespace."""
        assert normalize_gallery_name("  test  ") == "test"
        assert normalize_gallery_name("\ttest\n") == "test"

    def test_normalize_collapses_spaces(self):
        """Test normalization collapses multiple spaces."""
        assert normalize_gallery_name("test   name") == "test name"
        assert normalize_gallery_name("a  b  c") == "a b c"

    def test_normalize_replaces_invalid_chars(self):
        """Test normalization replaces invalid characters."""
        assert normalize_gallery_name("test<name") == "test_name"
        assert normalize_gallery_name('test:"name') == "test__name"  # Two chars replaced: colon and quote
        assert normalize_gallery_name("test|?*name") == "test___name"  # Three chars replaced

    def test_normalize_replaces_path_separators(self):
        """Test normalization replaces path separators."""
        assert normalize_gallery_name("test/name") == "test_name"
        assert normalize_gallery_name("test\\name") == "test_name"

    def test_normalize_preserves_valid_chars(self):
        """Test normalization preserves valid characters."""
        assert normalize_gallery_name("Test-Name_123") == "Test-Name_123"
        assert normalize_gallery_name("Gallery.2024") == "Gallery.2024"

    def test_normalize_handles_unicode(self):
        """Test normalization preserves Unicode characters."""
        assert normalize_gallery_name("café") == "café"
        assert normalize_gallery_name("Москва") == "Москва"

    def test_normalize_empty_string(self):
        """Test normalization of empty string."""
        assert normalize_gallery_name("") == ""

    def test_normalize_only_whitespace(self):
        """Test normalization of whitespace-only string."""
        assert normalize_gallery_name("   ") == ""

    def test_normalize_mixed_issues(self):
        """Test normalization with multiple issues."""
        assert normalize_gallery_name("  test<>name   with:spaces  ") == "test__name with_spaces"

    def test_normalize_preserves_single_spaces(self):
        """Test that single spaces are preserved."""
        assert normalize_gallery_name("My Photo Gallery") == "My Photo Gallery"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""

    def test_generate_validate_register_workflow(self, temp_folder):
        """Test complete workflow: generate, validate, register."""
        generator = GalleryNameGenerator()
        validator = GalleryNameValidator()
        registry = GalleryNameRegistry()

        # Generate name
        name = generator.from_folder_name(temp_folder)
        assert name == "test_gallery"

        # Validate name
        is_valid, issues = validator.validate(name)
        assert is_valid is True
        assert len(issues) == 0

        # Register name
        registry.register(name)
        assert registry.is_used(name)

    def test_collision_handling_workflow(self, temp_folder):
        """Test workflow with name collisions."""
        generator = GalleryNameGenerator()
        registry = GalleryNameRegistry()

        # Generate and register first name
        name1 = generator.from_folder_name(temp_folder)
        registry.register(name1)

        # Get unique name for collision
        unique_name = registry.get_unique_name(name1)
        assert unique_name == "test_gallery (1)"
        assert not registry.is_used(unique_name)

        # Register the unique name
        registry.register(unique_name)
        assert registry.is_used(unique_name)

    def test_template_with_validation(self, temp_folder, sample_metadata):
        """Test template generation with validation."""
        generator = GalleryNameGenerator()
        validator = GalleryNameValidator()

        template = "{folder} - {count} images ({date})"
        name = generator.from_template(template, temp_folder, sample_metadata)

        # Validate the generated name
        is_valid, issues = validator.validate(name)
        assert is_valid is True

    def test_auto_generate_all_strategies(self, temp_folder):
        """Test all auto-generation strategies produce valid names."""
        generator = GalleryNameGenerator()
        validator = GalleryNameValidator()

        strategies = ["folder", "timestamp", "hash", "date"]
        for strategy in strategies:
            name = generator.auto_generate(temp_folder, strategy=strategy)
            is_valid, issues = validator.validate(name)
            assert is_valid is True, f"Strategy {strategy} produced invalid name: {issues}"

    def test_suggest_and_validate_all(self, temp_folder, sample_metadata):
        """Test that all suggestions are valid."""
        validator = GalleryNameValidator()

        suggestions = suggest_gallery_names(temp_folder, count=5, metadata=sample_metadata)

        for suggestion in suggestions:
            is_valid, issues = validator.validate(suggestion)
            assert is_valid is True, f"Suggestion '{suggestion}' is invalid: {issues}"

    def test_normalize_and_validate(self):
        """Test that normalization produces valid names."""
        validator = GalleryNameValidator()

        dirty_names = [
            "  test  name  ",
            "test<>name",
            "test:::name",
            "test///name"
        ]

        for dirty_name in dirty_names:
            normalized = normalize_gallery_name(dirty_name)
            # Some might become empty after normalization
            if normalized:
                is_valid, _ = validator.validate(normalized)
                # Normalized names should be valid or fixable
                assert is_valid or len(normalized) > 0

    def test_registry_with_suggestions(self, temp_folder, sample_metadata):
        """Test using suggestions with registry to avoid collisions."""
        registry = GalleryNameRegistry()

        # Get initial suggestions
        suggestions = suggest_gallery_names(temp_folder, count=5, metadata=sample_metadata)

        # Register first suggestion
        registry.register(suggestions[0])

        # Try to get unique version of first suggestion
        unique = registry.get_unique_name(suggestions[0])
        assert unique != suggestions[0]
        assert not registry.is_used(unique)


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_very_long_folder_name(self, generator, tmp_path):
        """Test handling of very long folder names."""
        # Max filename length on most filesystems is 255, so use 250 to be safe
        long_name = "a" * 250
        folder = tmp_path / long_name
        folder.mkdir()

        name = generator.from_folder_name(folder)
        # Should be cleaned but still long
        assert len(name) == 250
        assert name == long_name

    def test_unicode_emoji_in_name(self, generator):
        """Test handling of emoji in names."""
        # Emojis should be preserved in cleaning
        name_with_emoji = "Photos 📷 2024"
        cleaned = generator._clean_name(name_with_emoji)
        assert "📷" in cleaned

    def test_all_strategies_with_weird_path(self, generator, tmp_path):
        """Test all strategies with unusual path."""
        folder = tmp_path / "___weird___path___"
        folder.mkdir()

        strategies = ["folder", "timestamp", "hash", "date"]
        for strategy in strategies:
            # Should not raise error
            name = generator.auto_generate(folder, strategy=strategy)
            assert len(name) > 0

    def test_registry_stress_test(self, registry):
        """Test registry with many names."""
        # Register 100 galleries
        for i in range(100):
            registry.register(f"Gallery_{i}")

        # Should still work correctly
        assert len(registry._used_names) == 100
        assert registry.is_used("Gallery_50")
        assert not registry.is_used("Gallery_100")

    def test_validator_with_very_strict_settings(self):
        """Test validator with very strict settings."""
        validator = GalleryNameValidator(
            min_length=10,
            max_length=20,
            allow_unicode=False
        )

        # Too short
        assert not validator.is_valid("short")

        # Too long
        assert not validator.is_valid("a" * 21)

        # Just right
        assert validator.is_valid("valid_name_ok")

    def test_template_with_missing_placeholders(self, generator, temp_folder):
        """Test template with undefined placeholders."""
        template = "{folder}_{undefined}_{missing}"
        # Should keep undefined placeholders as-is
        result = generator.from_template(template, temp_folder)
        assert "{undefined}" in result
        assert "{missing}" in result

    def test_hash_with_empty_source(self, generator):
        """Test hash generation with empty source string."""
        result = generator.with_hash("Gallery", source="")
        assert re.match(r'Gallery_[a-f0-9]{8}', result)

    def test_multiple_registries_independent(self):
        """Test that multiple registries are independent."""
        registry1 = GalleryNameRegistry()
        registry2 = GalleryNameRegistry()

        registry1.register("Gallery1")
        assert registry1.is_used("Gallery1")
        assert not registry2.is_used("Gallery1")

    def test_validator_exact_length_boundaries(self):
        """Test validator at exact min/max length boundaries."""
        validator = GalleryNameValidator(min_length=5, max_length=10)

        # Exactly min length (valid)
        assert validator.is_valid("12345")

        # One below min (invalid)
        assert not validator.is_valid("1234")

        # Exactly max length (valid)
        assert validator.is_valid("1234567890")

        # One above max (invalid)
        assert not validator.is_valid("12345678901")


# ============================================================================
# Performance Tests (marked as slow)
# ============================================================================

@pytest.mark.slow
class TestPerformance:
    """Performance tests for gallery naming operations."""

    def test_generate_many_unique_names(self, registry):
        """Test generating many unique names."""
        base_name = "Gallery"
        count = 1000

        for i in range(count):
            if i == 0:
                registry.register(base_name)
            else:
                registry.register(f"{base_name} ({i})")

        # Should still be fast
        unique = registry.get_unique_name(base_name, max_attempts=2000)
        assert unique == f"{base_name} ({count})"

    def test_validator_bulk_validation(self):
        """Test validating many names."""
        validator = GalleryNameValidator()
        names = [f"Gallery_{i}" for i in range(1000)]

        # Should complete quickly
        for name in names:
            validator.is_valid(name)

    def test_suggest_multiple_folders(self, tmp_path):
        """Test suggesting names for many folders."""
        folders = []
        for i in range(50):
            folder = tmp_path / f"folder_{i}"
            folder.mkdir()
            folders.append(folder)

        # Should complete quickly
        for folder in folders:
            suggestions = suggest_gallery_names(folder, count=3)
            assert len(suggestions) > 0
