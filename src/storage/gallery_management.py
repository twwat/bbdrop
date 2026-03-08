"""Gallery management: unnamed gallery tracking, renaming, existence checks, filename building."""

import os
import glob
import configparser

from src.utils.logger import log
from src.utils.paths import (
    get_config_path,
    get_central_storage_path,
    read_config,
)


def save_unnamed_gallery(gallery_id, intended_name):
    """Save unnamed gallery for later renaming (now uses database for speed)"""
    try:
        from src.storage.database import QueueStore
        store = QueueStore()
        store.add_unnamed_gallery(gallery_id, intended_name)
        log(f"Gallery '{gallery_id}' to be renamed '{intended_name}' later", level="debug", category="renaming")
    except Exception as e:
        # Fallback to config file
        log(f"Database save failed, using config file fallback: {e}", level="error", category="renaming")
        config = configparser.ConfigParser()
        config_file = get_config_path()

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')

        if 'UNNAMED_GALLERIES' not in config:
            config['UNNAMED_GALLERIES'] = {}

        config['UNNAMED_GALLERIES'][gallery_id] = intended_name

        with open(config_file, 'w') as f:
            config.write(f)

        log(f"Saved unnamed gallery {gallery_id} for later renaming to '{intended_name}'", level="info", category="renaming")

def sanitize_gallery_name(name):
    """Remove invalid characters from gallery name"""
    import re
    # Keep alphanumeric, spaces, hyphens, dashes, round brackets, periods, underscores
    # Remove everything else (square brackets, number signs, etc.)
    sanitized = re.sub(r'[^a-zA-Z0-9,\.\s\-_\(\)]', '', name)
    # Remove multiple spaces
    sanitized = re.sub(r'\s+', ' ', sanitized)
    # Trim spaces
    sanitized = sanitized.strip()
    return sanitized

def build_gallery_filenames(gallery_name, gallery_id):
    """Return standardized filenames for gallery artifacts.
    - JSON filename: {Gallery Name}_{GalleryID}.json
    - BBCode filename: {Gallery Name}_{GalleryID}_bbcode.txt
    Returns (gallery_name, json_filename, bbcode_filename).
    """
    # Use gallery name directly - no sanitization for filenames
    json_filename = f"{gallery_name}_{gallery_id}.json"
    bbcode_filename = f"{gallery_name}_{gallery_id}_bbcode.txt"
    return gallery_name, json_filename, bbcode_filename

def check_if_gallery_exists(folder_name):
    """Check if gallery files already exist for this folder"""
    central_path = get_central_storage_path()

    # Check central location
    central_files = glob.glob(os.path.join(central_path, f"{folder_name}_*_bbcode.txt")) + \
                    glob.glob(os.path.join(central_path, f"{folder_name}_*.json"))

    # Check within .uploaded subfolder directly under this folder
    folder_files = [
        os.path.join(folder_name, ".uploaded", f"{folder_name}_*.json"),
        os.path.join(folder_name, ".uploaded", f"{folder_name}_*_bbcode.txt")
    ]

    existing_files = []
    existing_files.extend(central_files)
    for pattern in folder_files:
        existing_files.extend(glob.glob(pattern))

    return existing_files

def get_unnamed_galleries():
    """Get list of unnamed galleries from database (much faster than config file)"""
    try:
        from src.storage.database import QueueStore
        store = QueueStore()
        return store.get_unnamed_galleries()
    except Exception:
        # Fallback to config file if database fails
        config = read_config()
        if 'UNNAMED_GALLERIES' in config:
            return dict(config['UNNAMED_GALLERIES'])
        return {}

def rename_all_unnamed_with_session(uploader: 'ImxToUploader') -> int:
    """Rename all unnamed galleries using an already logged-in uploader session.
    Returns the number of successfully renamed galleries. Stops early on HTTP 403 or DDoS-Guard block.
    """
    unnamed_galleries = get_unnamed_galleries()
    if not unnamed_galleries:
        return 0
    success_count = 0
    attempted = 0
    for gallery_id, intended_name in unnamed_galleries.items():
        attempted += 1
        ok = uploader.rename_gallery_with_session(gallery_id, intended_name)
        # If blocked by DDoS-Guard or got 403, stop further attempts
        status = getattr(uploader, '_last_rename_status_code', None)
        ddos = bool(getattr(uploader, '_last_rename_ddos', False))
        if status == 403 or ddos:
            # If we used cookies and credentials exist, try credentials-only once for this gallery
            try:
                last_method = getattr(uploader, 'last_login_method', None)
            except Exception:
                last_method = None
            has_creds = bool(getattr(uploader, 'username', None) and getattr(uploader, 'password', None))
            retried_ok = False
            if last_method == 'cookies' and has_creds:
                if getattr(uploader, 'login_with_credentials_only', None) and uploader.login_with_credentials_only():
                    retried_ok = uploader.rename_gallery_with_session(gallery_id, intended_name)
                    status = getattr(uploader, '_last_rename_status_code', None)
                    ddos = bool(getattr(uploader, '_last_rename_ddos', False))
            if retried_ok:
                ok = True
            else:
                # Hard stop further renames to avoid hammering while blocked
                try:
                    if hasattr(uploader, 'worker_thread') and uploader.worker_thread is not None:
                        log(f"Stopping auto-rename due to {'DDoS-Guard' if ddos else 'HTTP 403'}", level="debug", category="renaming")
                except Exception:
                    pass
                # Do not continue processing additional galleries
                break
        if ok:
            try:
                if hasattr(uploader, 'worker_thread') and uploader.worker_thread is not None:
                    log(f"Successfully renamed gallery '{gallery_id}' to '{intended_name}'", level="info", category="renaming")
                    try:
                        # Notify GUI to update Renamed column if available
                        if hasattr(uploader.worker_thread, 'gallery_renamed'):
                            uploader.worker_thread.gallery_renamed.emit(gallery_id)
                    except Exception:
                        pass
            except Exception:
                pass
            # Only remove if rename succeeded definitively
            remove_unnamed_gallery(gallery_id)
            success_count += 1
        else:
            # Log explicit failure for visibility
            try:
                if hasattr(uploader, 'worker_thread') and uploader.worker_thread is not None:
                    reason = "DDoS-Guard" if ddos else (f"HTTP {status}" if status else "unknown error")
                    log(f"Failed to rename gallery '{gallery_id}' to '{intended_name}' ({reason})", level="warning", category="renaming")
            except Exception:
                pass
            # Keep it in unnamed list for future attempts
    return success_count

def check_gallery_renamed(gallery_id):
    """Check if a gallery has been renamed (not in unnamed galleries list)"""
    try:
        from src.storage.database import QueueStore
        store = QueueStore()
        unnamed_galleries = store.get_unnamed_galleries()
        return gallery_id not in unnamed_galleries
    except Exception:
        # Fallback to config file if database fails
        unnamed_galleries = get_unnamed_galleries()
        return gallery_id not in unnamed_galleries

def remove_unnamed_gallery(gallery_id):
    """Remove gallery from unnamed list after successful renaming (now uses database)"""
    try:
        from src.storage.database import QueueStore
        store = QueueStore()
        removed = store.remove_unnamed_gallery(gallery_id)
        if removed:
            log(f"Removed {gallery_id} from unnamed galleries list", level="debug", category="renaming")
    except Exception as e:
        # Fallback to config file
        log(f"Database removal failed, using config file fallback: {e}", level="warning", category="renaming")
        config = configparser.ConfigParser()
        config_file = get_config_path()

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')

            if 'UNNAMED_GALLERIES' in config and gallery_id in config['UNNAMED_GALLERIES']:
                del config['UNNAMED_GALLERIES'][gallery_id]

                with open(config_file, 'w') as f:
                    config.write(f)
