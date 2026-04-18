"""Unit tests for src/gui/layout_manager.py."""

import os
import pytest
from unittest.mock import MagicMock

# Headless Qt — conftest.py sets this, but be explicit
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication exists for the module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestLayoutManagerSkeleton:
    """Sanity checks on the LayoutManager skeleton."""

    def test_layout_manager_is_importable(self, qapp):
        from src.gui.layout_manager import LayoutManager
        assert LayoutManager is not None

    def test_layout_manager_instantiable_with_mock_mw(self, qapp):
        from src.gui.layout_manager import LayoutManager
        mw = MagicMock()
        lm = LayoutManager(mw)
        assert lm is not None
