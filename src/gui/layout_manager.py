"""Dock-based layout management for BBDrop main window.

LayoutManager owns construction of all QDockWidget panels, applies preset
layouts via QMainWindow.saveState()/restoreState(), and provides Reset Layout.

See docs/superpowers/specs/2026-04-17-customizable-layout-design.md for design.
"""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QByteArray, QObject

from src.utils.logger import log

if TYPE_CHECKING:
    from src.gui.main_window import BBDropGUI


class LayoutManager(QObject):
    """Constructs and manages dock widgets for the BBDrop main window.

    The main window's Upload Queue is the central widget (not a dock).
    Six non-queue panels (Quick Settings, Hosts, Log, Progress, Info, Speed)
    are each wrapped in a QDockWidget and placed per the Classic default layout.

    Attributes:
        _mw: Reference to the main BBDropGUI window.
    """

    def __init__(self, main_window: "BBDropGUI"):
        super().__init__()
        self._mw = main_window

    def build(self) -> None:
        """Construct all dock widgets and place them in the Classic default layout.

        Assigns widget references on self._mw (e.g., mw.log_text, mw.worker_status_widget)
        so existing controllers and signal handlers find them unchanged.
        """
        raise NotImplementedError  # Implemented in Task 3

    def apply_preset(self, name: str) -> None:
        """Apply a named preset from layout_presets.PRESETS.

        Args:
            name: One of "classic", "focused_queue", "two_column".

        Raises:
            KeyError: If name is not a known preset.
        """
        from src.gui.layout_presets import PRESETS

        payload_b64 = PRESETS[name]  # raises KeyError on unknown name
        if not payload_b64:
            log(
                f"Preset '{name}' has no captured payload; skipping apply",
                level="warning",
                category="ui",
            )
            return

        state = QByteArray.fromBase64(payload_b64)
        if not self._mw.restoreState(state):
            log(
                f"Preset '{name}' could not be applied (restoreState returned False); "
                "current layout unchanged",
                level="warning",
                category="ui",
            )

    def reset_layout(self) -> None:
        """Restore the Classic default layout."""
        self.apply_preset("classic")
