#!/usr/bin/env python3
"""
Archive processing coordinator
Orchestrates extraction, folder selection, and cleanup
"""

from pathlib import Path
from typing import Callable, Optional

from src.services.archive_service import ArchiveService
from src.utils.archive_utils import get_archive_name


class ArchiveCoordinator:
    """Coordinates archive processing workflow"""

    def __init__(self, archive_service: ArchiveService, parent_widget=None,
                 folder_selector_factory: Optional[Callable] = None):
        """Initialize coordinator

        Args:
            archive_service: Service for extraction and cleanup
            parent_widget: Parent widget for dialogs
            folder_selector_factory: Callable(archive_name, folders, parent) that
                returns a dialog with .exec() and .get_selected_folders() methods.
                Injected by the GUI layer to avoid importing dialog classes here.
        """
        self.service = archive_service
        self.parent = parent_widget
        self._folder_selector_factory = folder_selector_factory

    def process_archive(self, archive_path: str | Path) -> Optional[list[Path]]:
        """Process archive and return selected folders

        Args:
            archive_path: Path to archive file

        Returns:
            List of selected folder paths, or None if cancelled/failed
        """
        archive_path = Path(archive_path)
        archive_name = get_archive_name(archive_path)

        # Extract archive
        temp_dir = self.service.extract_archive(archive_path)
        if not temp_dir:
            return None

        # Get folders with files (queue manager will validate images)
        folders = self.service.get_folders(temp_dir)

        if not folders:
            # No folders found - cleanup and return
            self.service.cleanup_temp_dir(temp_dir)
            return None

        # If only one folder, return it directly
        if len(folders) == 1:
            return folders

        # Multiple folders - show selector dialog via factory
        if self._folder_selector_factory:
            dialog = self._folder_selector_factory(archive_name, folders, self.parent)
            if dialog.exec():
                selected = dialog.get_selected_folders()
                if selected:
                    return selected

        # User cancelled, no selection, or no factory available
        self.service.cleanup_temp_dir(temp_dir)
        return None
