"""Tests for MediaStrategy ABC and factory."""
import pytest
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

    def test_video_strategy_methods_raise(self):
        s = VideoStrategy()
        with pytest.raises(NotImplementedError):
            s.scan("/tmp")
        with pytest.raises(NotImplementedError):
            s.prepare_upload(None, {})
        with pytest.raises(NotImplementedError):
            s.generate_primary_content(None, {})
        with pytest.raises(NotImplementedError):
            s.get_template_placeholders(None)


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
