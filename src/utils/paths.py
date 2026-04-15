"""
Path and configuration helpers for bbdrop.

Extracted from bbdrop.py — provides version info, project root resolution,
config file access, and central store path management.
"""

import os
import sys
import platform
import configparser

from src.utils.logger import log

__version__ = "0.9.7"  # Application version number

# Lazy User-Agent string builder to avoid platform.system() hang during module import
# (platform.system() can hang on some Windows systems, breaking splash screen initialization)
_user_agent_cache = None

def get_user_agent() -> str:
    """Get User-Agent string, building it lazily on first call to avoid import-time hangs."""
    global _user_agent_cache
    if _user_agent_cache is None:
        try:
            _system = platform.system()
            _release = platform.release()
            _machine = platform.machine()
            _version = platform.version()
            _user_agent_cache = f"Mozilla/5.0 (BBDrop {__version__}; {_system} {_release} {_version}; {_machine}; rv:141.0) Gecko/20100101 Firefox/141.0"
        except Exception:
            # Fallback if platform calls fail
            _user_agent_cache = f"Mozilla/5.0 (BBDrop {__version__}; Windows; rv:141.0) Gecko/20100101 Firefox/141.0"
    return _user_agent_cache

def get_version() -> str:
    return __version__

def get_project_root() -> str:
    """Return the project root directory.

    When running as PyInstaller frozen executable:
        Returns the directory containing the .exe (where assets/, docs/, src/ are located)
    When running as Python script:
        Returns the directory containing bbdrop.py
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller executable - use .exe location
        # This ensures we find assets/, docs/, src/ next to the .exe
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # Running as Python script - use bbdrop.py location
        # Navigate up from src/utils/paths.py to the project root
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_base_path() -> str:
    """Get the base path for all app data (config, galleries, templates).

    Checks QSettings for custom base path (bootstrap), falls back to default ~/.bbdrop
    """
    try:
        # Check QSettings for custom base path (bootstrap location)
        from PyQt6.QtCore import QSettings
        settings = QSettings("BBDropUploader", "BBDropGUI")
        custom_base = settings.value("config/base_path", "", type=str)

        if custom_base and os.path.isdir(custom_base):
            return custom_base
    except Exception:
        pass  # QSettings not available (CLI mode)

    # Default location
    return os.path.join(os.path.expanduser("~"), ".bbdrop")


def get_config_path() -> str:
    """Return the canonical path to the application's config file."""
    base_dir = get_base_path()
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "bbdrop.ini")

def read_config() -> configparser.ConfigParser:
    """Read the application config file with proper encoding.

    Returns:
        ConfigParser instance with loaded config (empty if file doesn't exist)
    """
    config = configparser.ConfigParser()
    config_file = get_config_path()
    if os.path.exists(config_file):
        config.read(config_file, encoding='utf-8')
    return config

def migrate_from_imxup() -> bool:
    """Migrate settings and data from old imxup to new bbdrop location.

    Copies settings and data from old location to new location and migrates
    QSettings from ImxUploader/imxup to BBDropUploader/bbdrop namespaces.
    Also migrates keyring credentials from 'imxup' to 'bbdrop' service.

    Handles custom base paths configured in old QSettings.

    Returns:
        True if migration was performed, False if not needed or failed.
    """
    import shutil

    home = os.path.expanduser("~")

    # First, migrate QSettings (registry/config files) to get custom base path if it exists
    old_custom_base = None
    try:
        from PyQt6.QtCore import QSettings

        # Check for custom base path in OLD settings FIRST
        old_main_settings = QSettings("ImxUploader", "ImxUploadGUI")
        old_custom_base = old_main_settings.value("config/base_path", "", type=str)

        # Only migrate QSettings if old keys exist and new keys don't yet
        new_main_settings = QSettings("BBDropUploader", "BBDropGUI")
        if old_main_settings.allKeys() and not new_main_settings.contains("_migrated_from_imxup"):
            old_qsettings_pairs = [
                ("ImxUploader", "ImxUploadGUI", "BBDropUploader", "BBDropGUI"),
                ("ImxUploader", "QueueManager", "BBDropUploader", "QueueManager"),
                ("ImxUploader", "Stats", "BBDropUploader", "Stats"),
                ("ImxUploader", "Settings", "BBDropUploader", "Settings"),
                ("ImxUploader", "TabManager", "BBDropUploader", "TabManager"),
                ("imxup", "imxup", "bbdrop", "bbdrop"),
            ]

            for old_org, old_app, new_org, new_app in old_qsettings_pairs:
                old_settings = QSettings(old_org, old_app)
                new_settings = QSettings(new_org, new_app)

                for key in old_settings.allKeys():
                    value = old_settings.value(key)
                    if value is not None:
                        new_settings.setValue(key, value)

                new_settings.sync()

                # Remove old keys so they can't interfere
                old_settings.clear()
                old_settings.sync()

            # Mark migration as done so it never runs again
            new_main_settings.setValue("_migrated_from_imxup", True)
            new_main_settings.sync()
            log("QSettings migrated from ImxUploader to BBDropUploader", level="info", category="migration")
    except Exception:
        pass  # QSettings migration is optional, continue with file migration

    # Determine old and new paths (respecting custom base path if it was set)
    if old_custom_base and os.path.isdir(old_custom_base):
        old_path = old_custom_base
        # Keep the custom path for new location too (already migrated in QSettings)
        new_path = old_custom_base  # Same location, just rename files
        log(f"Using custom base path from old settings: {old_custom_base}", level="info", category="migration")
    else:
        old_path = os.path.join(home, ".imxup")
        new_path = os.path.join(home, ".bbdrop")

    # Check if migration is needed
    if not os.path.exists(old_path):
        return False  # No old data to migrate

    # If using same custom path, only need to rename files, not check if target exists
    if old_path == new_path:
        # Same directory - just rename imxup files to bbdrop
        files_to_rename = [
            ("imxup.ini", "bbdrop.ini"),
            ("imxup.db", "bbdrop.db"),
            ("imxup.db-shm", "bbdrop.db-shm"),
            ("imxup.db-wal", "bbdrop.db-wal"),
        ]

        renamed_any = False
        for old_name, new_name in files_to_rename:
            old_file = os.path.join(old_path, old_name)
            new_file = os.path.join(new_path, new_name)
            if os.path.exists(old_file) and not os.path.exists(new_file):
                try:
                    os.rename(old_file, new_file)
                    renamed_any = True
                except Exception:
                    pass

        if renamed_any:
            log(f"Migrated files in custom location: {old_path}", level="info", category="migration")
        return renamed_any

    # Different paths - check if new location already has data
    if os.path.exists(new_path) and os.listdir(new_path):
        return False  # New location already has data

    try:
        # Create new directory
        os.makedirs(new_path, exist_ok=True)

        # Copy data files (database, templates, galleries, etc.)
        for item in os.listdir(old_path):
            old_item = os.path.join(old_path, item)
            new_item = os.path.join(new_path, item)

            # Rename imxup files to bbdrop
            if item == "imxup.ini":
                new_item = os.path.join(new_path, "bbdrop.ini")
            elif item == "imxup.db":
                new_item = os.path.join(new_path, "bbdrop.db")
            elif item == "imxup.db-shm":
                new_item = os.path.join(new_path, "bbdrop.db-shm")
            elif item == "imxup.db-wal":
                new_item = os.path.join(new_path, "bbdrop.db-wal")

            if os.path.isdir(old_item):
                shutil.copytree(old_item, new_item, dirs_exist_ok=True)
            else:
                shutil.copy2(old_item, new_item)

        # Migrate QSettings (Windows registry or ini files) — guarded by _migrated_from_imxup flag
        # (The early migration block above already handles this, but keep as fallback
        #  for the file-copy path which only runs when old_path exists and new_path is empty)
        try:
            from PyQt6.QtCore import QSettings
            new_check = QSettings("BBDropUploader", "BBDropGUI")
            if not new_check.contains("_migrated_from_imxup"):
                old_qsettings_pairs = [
                    ("ImxUploader", "ImxUploadGUI", "BBDropUploader", "BBDropGUI"),
                    ("ImxUploader", "QueueManager", "BBDropUploader", "QueueManager"),
                    ("ImxUploader", "Stats", "BBDropUploader", "Stats"),
                    ("ImxUploader", "Settings", "BBDropUploader", "Settings"),
                    ("ImxUploader", "TabManager", "BBDropUploader", "TabManager"),
                    ("imxup", "imxup", "bbdrop", "bbdrop"),
                ]

                for old_org, old_app, new_org, new_app in old_qsettings_pairs:
                    old_settings = QSettings(old_org, old_app)
                    new_settings = QSettings(new_org, new_app)

                    for key in old_settings.allKeys():
                        value = old_settings.value(key)
                        if value is not None:
                            new_settings.setValue(key, value)

                    new_settings.sync()

                    old_settings.clear()
                    old_settings.sync()

                new_check.setValue("_migrated_from_imxup", True)
                new_check.sync()
        except Exception:
            pass  # QSettings migration is optional

        # Migrate keyring credentials
        try:
            import keyring
            cookies = keyring.get_password("imxup", "session_cookies")
            if cookies:
                keyring.set_password("bbdrop", "session_cookies", cookies)
        except Exception:
            pass  # Keyring migration is optional

        log(f"Migrated settings from {old_path} to {new_path}", level="info", category="migration")
        return True

    except Exception as e:
        log(f"Migration failed: {e}", level="error", category="migration")
        return False


def _unique_destination_path(dest_dir: str, filename: str) -> str:
    """Generate a unique destination path within dest_dir.
    If a file with the same name exists, append _1, _2, ... before the extension.
    """
    name, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    if not os.path.exists(candidate):
        return candidate
    suffix = 1
    while True:
        new_name = f"{name}_{suffix}{ext}"
        candidate = os.path.join(dest_dir, new_name)
        if not os.path.exists(candidate):
            return candidate
        suffix += 1

def get_default_central_store_base_path():
    """Return the default central store BASE path. Alias for get_base_path default."""
    return os.path.join(os.path.expanduser("~"), ".bbdrop")


def get_central_store_base_path():
    """Get the configured central store BASE path (parent of galleries/templates)."""
    base_path = get_base_path()
    os.makedirs(base_path, exist_ok=True)
    return base_path


def get_central_storage_path():
    """Get the galleries subfolder inside the central store base path.

    Ensures the directory exists before returning.
    """
    base = get_central_store_base_path()
    galleries_path = os.path.join(base, "galleries")
    os.makedirs(galleries_path, exist_ok=True)
    return galleries_path

def get_video_artifacts_path() -> str:
    """Return path for video artifacts (~/.bbdrop/videos/).

    Ensures the directory exists before returning.
    """
    base = get_central_store_base_path()
    videos_path = os.path.join(base, "videos")
    os.makedirs(videos_path, exist_ok=True)
    return videos_path


def load_user_defaults():
    """Load user defaults from config file

    Returns:
        Dictionary of user settings with defaults
    """
    # Default values for all settings
    defaults = {
        'thumbnail_size': 3,
        'thumbnail_format': 2,
        'max_retries': 3,
        'parallel_batch_size': 4,
        'template_name': 'default',
        'confirm_delete': True,
        'auto_rename': True,
        'auto_start_upload': False,
        'auto_regenerate_bbcode': False,
        'store_in_uploaded': True,
        'store_in_central': True,
        'central_store_path': get_default_central_store_base_path(),
        'upload_connect_timeout': 30,
        'upload_read_timeout': 120,
        'use_median': True,
        'stats_exclude_outliers': False,
        'check_updates_on_startup': True,
        'default_image_host': 'imx',
        'archive_format': 'zip',
        'archive_compression': 'store',
        'archive_split_enabled': False,
        'archive_split_size_mb': 500,
        'archive_split_mode': 'fixed',
    }

    config = read_config()

    if 'DEFAULTS' in config:
            # Load integer settings
            for key in ['thumbnail_size', 'thumbnail_format', 'max_retries',
                       'parallel_batch_size', 'upload_connect_timeout', 'upload_read_timeout',
                       'archive_split_size_mb']:
                defaults[key] = config.getint('DEFAULTS', key, fallback=defaults[key])

            # Load boolean settings
            for key in ['confirm_delete', 'auto_rename', 'auto_start_upload',
                       'auto_regenerate_bbcode', 'store_in_uploaded', 'store_in_central',
                       'use_median', 'stats_exclude_outliers', 'check_updates_on_startup',
                       'archive_split_enabled']:
                defaults[key] = config.getboolean('DEFAULTS', key, fallback=defaults[key])

            # Load string settings
            defaults['template_name'] = config.get('DEFAULTS', 'template_name', fallback='default')
            defaults['default_image_host'] = config.get('DEFAULTS', 'default_image_host', fallback='imx')
            defaults['archive_format'] = config.get('DEFAULTS', 'archive_format', fallback='zip')
            defaults['archive_compression'] = config.get('DEFAULTS', 'archive_compression', fallback='store')
            defaults['archive_split_mode'] = config.get('DEFAULTS', 'archive_split_mode', fallback='fixed')

            # Load central store path with fallback handling
            try:
                defaults['central_store_path'] = config.get('DEFAULTS', 'central_store_path',
                                                           fallback=get_default_central_store_base_path())
            except Exception:
                defaults['central_store_path'] = get_default_central_store_base_path()

    return defaults
