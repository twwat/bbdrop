"""Unit tests for src/gui/layout_presets.py."""


class TestPresets:
    """Verify the PRESETS constant has the expected shape."""

    def test_presets_has_three_keys(self):
        from src.gui.layout_presets import PRESETS
        assert set(PRESETS.keys()) == {"classic", "focused_queue", "two_column"}

    def test_presets_values_are_bytes(self):
        from src.gui.layout_presets import PRESETS
        for name, value in PRESETS.items():
            assert isinstance(value, bytes), f"PRESETS[{name!r}] is not bytes"
