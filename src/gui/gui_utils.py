"""
GUI utility functions for imxup application.
Provides helper functions for common GUI operations.
"""

from typing import Optional
from PyQt6.QtWidgets import QWidget


def show_status_message(widget: QWidget, message: str, timeout: int = 2500) -> bool:
    """
    Show a message in the main window's status bar.

    Args:
        widget: Any QWidget (will traverse up to find main window)
        message: Message to display
        timeout: Duration in milliseconds (default 2500ms = 2.5 seconds)

    Returns:
        True if message was displayed, False otherwise

    Example:
        from src.gui.gui_utils import show_status_message
        show_status_message(self, "Settings saved successfully")
    """
    main_window = find_main_window(widget)
    if main_window and hasattr(main_window, 'statusBar'):
        status_bar = main_window.statusBar()
        if status_bar:
            status_bar.showMessage(message, timeout)
            return True

    return False


def add_log_message(widget: QWidget, message: str, include_timestamp: bool = True) -> bool:
    """
    Add a message to the main window's log viewer.

    Args:
        widget: Any QWidget (will traverse up to find main window)
        message: Message to log
        include_timestamp: Whether to prepend timestamp (default True)

    Returns:
        True if message was logged, False otherwise

    Example:
        from src.gui.gui_utils import add_log_message
        add_log_message(self, "Settings saved successfully")
        add_log_message(self, "[auth] Login successful")

    Message Categories (for filtering):
        [general], [auth], [uploads], [uploads:file], [uploads:gallery], [renaming]
    """
    main_window = find_main_window(widget)
    if main_window and hasattr(main_window, 'add_log_message'):
        if include_timestamp:
            from imxup import timestamp
            message = f"{timestamp()} {message}"
        main_window.add_log_message(message)
        return True

    return False


def find_main_window(widget: QWidget) -> Optional[QWidget]:
    """
    Find the main application window from any widget.

    Args:
        widget: Any QWidget in the application

    Returns:
        The main window (ImxUploadGUI) or None if not found

    Example:
        from src.gui.gui_utils import find_main_window
        main_window = find_main_window(self)
        if main_window:
            main_window.queue_manager.add_item(...)
    """
    # Look for the main window by checking for queue_manager attribute
    current = widget
    while current and not hasattr(current, 'queue_manager'):
        current = current.parent()

    return current
