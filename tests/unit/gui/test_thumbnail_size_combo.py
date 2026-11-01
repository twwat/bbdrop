"""Thumbnail size combos carry the host size ID, not a list position."""

import pytest
from PyQt6.QtWidgets import QComboBox

from src.gui.thumbnail_size_combo import (
    populate_thumbnail_size_combo,
    selected_thumbnail_size_id,
)

pytestmark = pytest.mark.unit

IMX_SIZES = [
    {"id": 1, "label": "100x100"},
    {"id": 6, "label": "150x150"},
    {"id": 2, "label": "180x180"},
    {"id": 3, "label": "250x250"},
    {"id": 4, "label": "300x300"},
    {"id": 5, "label": "600x600 (Cover)"},
]


@pytest.mark.parametrize("size_id", [1, 6, 2, 3, 4, 5])
def test_every_id_round_trips(qapp, size_id):
    combo = QComboBox()
    populate_thumbnail_size_combo(combo, IMX_SIZES, size_id)
    assert selected_thumbnail_size_id(combo) == size_id


def test_unknown_saved_value_selects_default(qapp):
    combo = QComboBox()
    populate_thumbnail_size_combo(combo, IMX_SIZES, 99)
    assert selected_thumbnail_size_id(combo) == 3


def test_none_saved_value_selects_default(qapp):
    combo = QComboBox()
    populate_thumbnail_size_combo(combo, IMX_SIZES, None)
    assert selected_thumbnail_size_id(combo) == 3


def test_labels_in_config_order(qapp):
    combo = QComboBox()
    populate_thumbnail_size_combo(combo, IMX_SIZES, 3)
    assert [combo.itemText(i) for i in range(combo.count())] == [s["label"] for s in IMX_SIZES]


def test_selected_label_matches_id(qapp):
    combo = QComboBox()
    populate_thumbnail_size_combo(combo, IMX_SIZES, 6)
    assert combo.currentText() == "150x150"


def test_repopulating_replaces_items(qapp):
    combo = QComboBox()
    populate_thumbnail_size_combo(combo, IMX_SIZES, 3)
    populate_thumbnail_size_combo(combo, IMX_SIZES, 1)
    assert combo.count() == len(IMX_SIZES)
    assert selected_thumbnail_size_id(combo) == 1


def test_population_does_not_emit_signals(qapp):
    combo = QComboBox()
    seen = []
    combo.currentIndexChanged.connect(seen.append)
    populate_thumbnail_size_combo(combo, IMX_SIZES, 6)
    assert seen == []


def test_empty_combo_yields_default(qapp):
    combo = QComboBox()
    assert selected_thumbnail_size_id(combo) == 3


def test_completion_worker_reads_size_id_from_real_combo(qapp):
    """A combo showing 150x150 must hand the worker size ID 6, not position 2."""
    from unittest.mock import Mock

    from src.processing.artifact_handler import CompletionWorker

    combo = QComboBox()
    populate_thumbnail_size_combo(combo, IMX_SIZES, 6)
    assert combo.currentText() == "150x150"

    gui_parent = Mock()
    gui_parent.thumbnail_size_combo = combo
    gui_parent.thumbnail_format_combo = Mock()
    gui_parent.thumbnail_format_combo.currentIndex = Mock(return_value=0)

    worker = CompletionWorker()
    try:
        worker.process_completion("/test/gallery", {"gallery_id": "x"}, gui_parent)
        _path, _results, _parent, ui_settings = worker.completion_queue.get(timeout=1.0)
    finally:
        worker.stop()
        worker.wait(2000)
    assert ui_settings["thumbnail_size"] == 6
