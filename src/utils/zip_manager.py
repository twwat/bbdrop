"""
Backward compatibility wrapper for ZIPManager.

New code should use ArchiveManager from archive_manager.py directly.
This module is kept so existing imports continue to work.
"""

from src.utils.archive_manager import ArchiveManager, get_archive_manager


class ZIPManager(ArchiveManager):
    """Legacy alias for ArchiveManager."""
    pass


def get_zip_manager():
    """Get global ArchiveManager instance (backward compat)."""
    return get_archive_manager()
