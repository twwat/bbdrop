"""Helpers for fixed-size thumbnail combos.

Each combo item carries the host's size ID as item data, so the saved value
no longer depends on the order of the items in the list.
"""

from PyQt6.QtWidgets import QComboBox

DEFAULT_THUMBNAIL_SIZE_ID = 3


def populate_thumbnail_size_combo(
    combo: QComboBox,
    sizes: list[dict],
    selected_id: int | None,
    default_id: int = DEFAULT_THUMBNAIL_SIZE_ID,
) -> None:
    """Fill ``combo`` with ``sizes`` (``{"id", "label"}``), selecting ``selected_id``.

    Falls back to ``default_id`` when ``selected_id`` is not in the list.
    Signals are blocked while the combo is rebuilt.
    """
    was_blocked = combo.blockSignals(True)
    try:
        combo.clear()
        for size in sizes:
            combo.addItem(size["label"], size["id"])
        idx = combo.findData(selected_id) if selected_id is not None else -1
        if idx < 0:
            idx = combo.findData(default_id)
        if idx >= 0:
            combo.setCurrentIndex(idx)
    finally:
        combo.blockSignals(was_blocked)


def selected_thumbnail_size_id(combo: QComboBox) -> int:
    """Return the size ID of the selected item, or the default when none is selected."""
    data = combo.currentData()
    return DEFAULT_THUMBNAIL_SIZE_ID if data is None else data
