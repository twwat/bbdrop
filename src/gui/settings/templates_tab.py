"""BBCode Templates settings tab -- manages template creation, editing, and selection."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal

from src.gui.dialogs.template_manager import TemplateManagerDialog
from src.utils.logger import log


class TemplatesTab(QWidget):
    """Self-contained BBCode Templates settings tab.

    Embeds a :class:`TemplateManagerDialog` as a child widget and delegates
    persistence to it.  Emits *dirty* whenever the embedded dialog reports
    pending changes so the orchestrator can track unsaved state.
    """

    dirty = pyqtSignal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the Templates settings UI by embedding TemplateManagerDialog."""
        layout = QVBoxLayout(self)

        # Determine which template is currently active in the main window
        active_template = "default"
        if self.parent_window and hasattr(self.parent_window, 'template_combo'):
            active_template = self.parent_window.template_combo.currentText()

        # Create and embed the template manager dialog as a child widget
        self.template_dialog = TemplateManagerDialog(self, current_template=active_template)
        self.template_dialog.setParent(self)
        self.template_dialog.setWindowFlags(Qt.WindowType.Widget)
        self.template_dialog.setModal(False)

        layout.addWidget(self.template_dialog)
        self.template_dialog.content_changed.connect(self.dirty.emit)

    # ------------------------------------------------------------------
    # Pending-changes API (used by orchestrator close/save logic)
    # ------------------------------------------------------------------

    def has_pending_changes(self) -> bool:
        """Return True if the embedded template manager has unsaved edits."""
        return (
            hasattr(self, 'template_dialog')
            and self.template_dialog.has_pending_changes()
        )

    def commit_all_changes(self) -> bool:
        """Commit pending template changes to disk and refresh the main window."""
        if not hasattr(self, 'template_dialog'):
            return True
        result = self.template_dialog.commit_all_changes()
        if result and self.parent_window and hasattr(self.parent_window, 'refresh_template_combo'):
            self.parent_window.refresh_template_combo()
        return result

    def discard_all_changes(self):
        """Discard all pending template changes."""
        if hasattr(self, 'template_dialog'):
            self.template_dialog.discard_all_changes()

    # ------------------------------------------------------------------
    # Settings persistence (matches other tab interfaces)
    # ------------------------------------------------------------------

    def save_settings(self) -> bool:
        """Save Templates tab settings (commit pending changes)."""
        try:
            return self.commit_all_changes()
        except Exception as e:
            log(f"Error saving template settings: {e}", level="warning", category="settings")
            return False

    def reload_settings(self):
        """Reload templates from disk, discarding unsaved changes."""
        self.discard_all_changes()
