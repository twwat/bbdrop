"""Tests for MixedMediaDialog."""
import pytest
from unittest.mock import patch, MagicMock


class TestMixedMediaDialog:
    def test_dialog_class_exists(self):
        from src.gui.dialogs.mixed_media_dialog import MixedMediaDialog
        assert MixedMediaDialog is not None

    def test_constants_defined(self):
        from src.gui.dialogs.mixed_media_dialog import MixedMediaDialog
        assert MixedMediaDialog.INCLUDE_IMAGES == "include"
        assert MixedMediaDialog.EXCLUDE_IMAGES == "exclude"
