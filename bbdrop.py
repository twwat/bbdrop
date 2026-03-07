#!/usr/bin/env python3
"""
imx.to gallery uploader
Upload image folders to imx.to as galleries
"""

import sys
import os
from datetime import datetime

# Console hiding moved to after GUI window appears (see line ~2220)

# Check for --debug flag early (before heavy imports)
DEBUG_MODE = '--debug' in sys.argv

def debug_print(msg):
    """Print debug message if DEBUG_MODE is enabled, otherwise print on same line"""
    # Skip printing if no console exists (console=False build)
    if sys.stdout is None:
        return
    try:
        if DEBUG_MODE:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"{timestamp} {msg}")
            sys.stdout.flush()
        else:
            # Print on same line, overwriting previous output
            try:
                terminal_width = os.get_terminal_size().columns
            except (OSError, AttributeError):
                terminal_width = 80  # Fallback for no terminal
            print(f"\r{msg:<{terminal_width}}", end='', flush=True)
    except (OSError, AttributeError):
        # Console operations failed, silently ignore
        pass

import requests
from requests.adapters import HTTPAdapter
import pycurl
import io
import json
import argparse
import sys
from typing import Optional

from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import time
import threading
from tqdm import tqdm
from src.utils.format_utils import format_binary_size, format_binary_rate
from src.utils.logger import log
from src.network.image_host_client import ImageHostClient
import configparser
import platform
import sqlite3
import glob
try:
    import winreg  # Windows-only
except ImportError:
    winreg = None  # Not available on Linux/Mac
import mimetypes

from src.network.imx_uploader import ImxToUploader

from src.utils.credentials import (
    CredentialDecryptionError,
    get_encryption_key,
    migrate_credentials_from_ini,
    setup_secure_password,
)

from src.utils.paths import (
    __version__,
    get_project_root,
    get_config_path,
    read_config,
    get_central_store_base_path,
    get_central_storage_path,
    load_user_defaults,
    migrate_from_imxup,
)
from src.utils.format_utils import timestamp

# GitHub repository info for update checker
GITHUB_OWNER = "twwat"
GITHUB_REPO = "bbdrop"


def create_windows_context_menu():
    """Create Windows context menu integration"""
    # Skip if not on Windows or winreg not available
    if winreg is None or platform.system() != 'Windows':
        return False

    try:
        # Resolve executables and scripts based on frozen/unfrozen state
        is_frozen = getattr(sys, 'frozen', False)

        if is_frozen:
            exe_path = sys.executable
            gui_script = f'"{exe_path}" --gui'
        else:
            gui_script = os.path.join(get_project_root(), 'bbdrop.py')
            python_exe = sys.executable or 'python.exe'
            if python_exe.lower().endswith('pythonw.exe'):
                pythonw_exe = python_exe
            else:
                pythonw_exe = python_exe.replace('python.exe', 'pythonw.exe')
                if not os.path.exists(pythonw_exe):
                    pythonw_exe = python_exe

        # Per-user registry (no admin required) — HKCU\Software\Classes
        hkcu_classes = r"Software\Classes"
        gui_key_path_dir = hkcu_classes + r"\Directory\shell\BBDrop"
        gui_key_dir = winreg.CreateKey(winreg.HKEY_CURRENT_USER, gui_key_path_dir)
        winreg.SetValue(gui_key_dir, "", winreg.REG_SZ, "Add to BBDrop")
        try:
            winreg.SetValueEx(gui_key_dir, "MultiSelectModel", 0, winreg.REG_SZ, "Document")
        except Exception:
            pass
        # Set icon to the exe/script so the menu entry shows the BBDrop icon
        if is_frozen:
            winreg.SetValueEx(gui_key_dir, "Icon", 0, winreg.REG_SZ, exe_path)
        gui_command_key_dir = winreg.CreateKey(gui_key_dir, "command")

        # Build command based on frozen/unfrozen state
        if is_frozen:
            gui_command = f'{gui_script} "%V"'
        else:
            gui_command = f'"{pythonw_exe}" "{gui_script}" --gui "%V"'

        winreg.SetValue(gui_command_key_dir, "", winreg.REG_SZ, gui_command)
        winreg.CloseKey(gui_command_key_dir)
        winreg.CloseKey(gui_key_dir)

        print("Context menu created successfully!")
        print("Right-click any folder and select 'Add to BBDrop'.")
        return True
        
    except Exception as e:
        log(f"Error creating context menu: {e}", level="error", category="ui")
        return False

def remove_windows_context_menu():
    """Remove Windows context menu integration"""
    # Skip if not on Windows or winreg not available
    if winreg is None or platform.system() != 'Windows':
        return False

    try:
        hkcu_classes = r"Software\Classes"

        # Clean up old HKCR keys (from previous installs that required admin)
        old_keys = [
            r"Directory\Background\shell\UploadToImx",
            r"Directory\Background\shell\UploadToImxGUI",
            r"Directory\shell\UploadToImx",
            r"Directory\shell\UploadToImxGUI",
        ]
        for key_path in old_keys:
            try:
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, key_path + r"\command")
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, key_path)
            except (FileNotFoundError, OSError):
                pass

        # Clean up old HKCU keys (same old names, in case they ended up here)
        for key_path in old_keys:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, hkcu_classes + "\\" + key_path + r"\command")
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, hkcu_classes + "\\" + key_path)
            except (FileNotFoundError, OSError):
                pass

        # Remove current BBDrop key
        try:
            bbdrop_key = hkcu_classes + r"\Directory\shell\BBDrop"
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, bbdrop_key + r"\command")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, bbdrop_key)
        except FileNotFoundError:
            pass
        
        log("Context menu removed successfully.", level="info", category="ui")
        return True
    except Exception as e:
        log(f"Error removing context menu: {e}", level="error", category="ui")
        return False


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


def get_template_path():
    """Get the template directory path (uses configured central store location)."""
    base_path = get_central_store_base_path()  # Use configured path, not hardcoded
    template_path = os.path.join(base_path, "templates")
    os.makedirs(template_path, exist_ok=True)
    return template_path

def get_default_template():
    """Get the default template content"""
    return "#folderName#\n#allImages#"

def load_templates():
    """Load all available templates from the template directory"""
    template_path = get_template_path()
    templates = {}
    
    # Add default template
    templates["default"] = get_default_template()

    # Add Extended Example template
    templates["Extended Example"] = """#folderName#
[hr][/hr]
[center][size=4][b][color=#11c153]#folderName#[/color][/b][/size]

[size=3][b][color="#888"]#pictureCount# IMAGES • #extension# • #width#x#height# • #folderSize# [/color] [/b][/font][/size]
[/center][hr][/hr]#allImages#
[if galleryLink][b]Gallery link[/b]: #galleryLink#[else][i][size=1]Sorry, no gallery link available.[/size][/i][/if]
ext1: [if ext1]#ext1#[else]no ext1 value set[/if]
ext2: [if ext2]#ext2#[else]no ext2 value set[/if]
ext3: [if ext3]#ext3#[else]no ext3 value set[/if]
ext4: [if ext4]#ext4#[else]no ext4 value set[/if]
custom1: [if custom1]#custom1#[else]no custom1 value set[/if]
custom2: [if custom2]#custom2#[else]no custom2 value set[/if]
custom3: [if custom3]#custom3#[else]no custom3 value set[/if]
custom4: [if custom4]#custom4#[else]no custom4 value set[/if]
[if hostLinks][b]Download links:[/b]
#hostLinks#[/if]"""

    # Load custom templates
    if os.path.exists(template_path):
        for filename in os.listdir(template_path):
            template_name = filename
            if template_name.startswith(".template"):
                template_name = template_name[10:]  # Remove ".template " prefix
            # Remove .txt extension if present
            if template_name.endswith('.template.txt'):
                template_name = template_name[:-13]
            if template_name.endswith('.txt'):
                template_name = template_name[:-4]
            if template_name:  # Skip empty names
                template_file = os.path.join(template_path, filename)
                try:
                    with open(template_file, 'r', encoding='utf-8') as f:
                        templates[template_name] = f.read()
                except Exception as e:
                    log(f"Could not load template '{template_name}': {e}", level="error", category="template")
    
    return templates

def process_conditionals(template_content, data):
    """Process conditional logic in templates before placeholder replacement.

    Supports two syntax forms:
    1. [if placeholder]content[/if] - shows content if placeholder value is non-empty
    2. [if placeholder=value]content[else]alternative[/if] - shows content if placeholder equals value

    Features:
    - Multiple inline conditionals on the same line
    - Nested conditionals (processed inside-out)
    - Empty lines from removed conditionals are stripped
    """
    import re

    # Process conditionals iteratively until no more found
    max_iterations = 50  # Prevent infinite loops
    iteration = 0

    while iteration < max_iterations:
        # Look for innermost conditional pattern (no nested [if] tags inside)
        # This regex matches [if...] followed by content WITHOUT another [if, then [/if]
        if_pattern = r'\[if\s+(\w+)(=([^\]]+))?\]((?:(?!\[if).)*?)\[/if\]'
        match = re.search(if_pattern, template_content, re.DOTALL)

        if not match:
            # No more conditionals found
            break

        placeholder_name = match.group(1)
        expected_value = match.group(3)  # None if no = comparison
        conditional_block = match.group(4)  # Content between [if] and [/if]

        # Get the actual value from data
        actual_value = data.get(placeholder_name, '')

        # Check for [else] clause (only at top level, not nested)
        else_pattern = r'^(.*?)\[else\](.*?)$'
        else_match = re.match(else_pattern, conditional_block, re.DOTALL)

        if else_match:
            true_content = else_match.group(1)
            false_content = else_match.group(2)
        else:
            true_content = conditional_block
            false_content = ''

        # Determine condition
        if expected_value is not None:
            # Equality check: [if placeholder=value]
            condition_met = (str(actual_value).strip() == expected_value.strip())
        else:
            # Existence check: [if placeholder]
            condition_met = bool(str(actual_value).strip())

        # Select content based on condition
        selected_content = true_content if condition_met else false_content

        # Replace the entire conditional block with selected content
        template_content = template_content[:match.start()] + selected_content + template_content[match.end():]

        iteration += 1

    # Clean up empty lines
    lines = template_content.split('\n')
    cleaned_lines = [line for line in lines if line.strip() or line == '']  # Keep intentional blank lines

    # Remove consecutive empty lines and leading/trailing empty lines
    result_lines = []
    prev_empty = False
    for line in cleaned_lines:
        is_empty = not line.strip()
        if is_empty:
            if not prev_empty and result_lines:  # Keep one empty line
                result_lines.append(line)
            prev_empty = True
        else:
            result_lines.append(line)
            prev_empty = False

    # Remove trailing empty lines
    while result_lines and not result_lines[-1].strip():
        result_lines.pop()

    return '\n'.join(result_lines)

def apply_template(template_content, data):
    """Apply a template with data replacement"""
    # Process conditional logic first (before placeholder replacement)
    result = process_conditionals(template_content, data)

    # Replace placeholders with actual data
    # hostLinks and allImages are expanded FIRST so that any main placeholders
    # embedded inside them (e.g. #folderSize# in a filehost bbcode_format)
    # get resolved in the second pass.
    composite_replacements = {
        '#hostLinks#': data.get('host_links', ''),
        '#allImages#': data.get('all_images', ''),
        '#cover#': data.get('cover', ''),
    }
    for placeholder, value in composite_replacements.items():
        result = result.replace(placeholder, str(value or ''))

    replacements = {
        '#folderName#': str(data.get('folder_name') or ''),
        '#width#': str(data.get('width', 0)),
        '#height#': str(data.get('height', 0)),
        '#longest#': str(data.get('longest', 0)),
        '#extension#': str(data.get('extension') or ''),
        '#pictureCount#': str(data.get('picture_count', 0)),
        '#folderSize#': str(data.get('folder_size') or ''),
        '#galleryLink#': str(data.get('gallery_link') or ''),
        '#custom1#': str(data.get('custom1') or ''),
        '#custom2#': str(data.get('custom2') or ''),
        '#custom3#': str(data.get('custom3') or ''),
        '#custom4#': str(data.get('custom4') or ''),
        '#ext1#': str(data.get('ext1') or ''),
        '#ext2#': str(data.get('ext2') or ''),
        '#ext3#': str(data.get('ext3') or ''),
        '#ext4#': str(data.get('ext4') or '')
    }
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value or ''))
    
    return result

def generate_bbcode_from_template(template_name, data):
    """Generate bbcode content using a specific template"""
    templates = load_templates()
    
    if template_name not in templates:
        log(f"Template '{template_name}' not found, using default", level="warning", category="template")
        template_name = "default"
    
    template_content = templates[template_name]
    return apply_template(template_content, data)


def save_gallery_artifacts(
    folder_path: str,
    results: dict,
    template_name: str = "default",
    store_in_uploaded: Optional[bool] = None,
    store_in_central: Optional[bool] = None,
    custom_fields: Optional[dict] = None,
    cover_bbcode: str = "",
) -> dict:
    """Save BBCode and JSON artifacts for a completed gallery.

    Parameters:
    - folder_path: path to the source image folder
    - results: the results dict returned by upload_folder (must contain keys used below)
    - template_name: which template to use for full bbcode generation
    - store_in_uploaded/store_in_central: overrides for storage locations. When None, read defaults
    - custom_fields: optional dict with custom1-4 and ext1-4 values

    Returns: dict with paths written: { 'uploaded': {'bbcode': str, 'json': str}, 'central': {...}}
    """
    # Determine storage preferences
    defaults = load_user_defaults()
    if store_in_uploaded is None:
        store_in_uploaded = defaults.get('store_in_uploaded', True)
    if store_in_central is None:
        store_in_central = defaults.get('store_in_central', True)

    gallery_id = results.get('gallery_id', '')
    gallery_name = results.get('gallery_name') or os.path.basename(folder_path)
    if not gallery_id or not gallery_name:
        return {}

    # Ensure .uploaded exists if needed
    uploaded_subdir = os.path.join(folder_path, ".uploaded")
    if store_in_uploaded:
        os.makedirs(uploaded_subdir, exist_ok=True)

    # Build filenames
    safe_gallery_name, json_filename, bbcode_filename = build_gallery_filenames(gallery_name, gallery_id)

    # Prepare template data from results for full bbcode
    total_size = results.get('total_size', 0)
    successful_images = results.get('successful_count', len(results.get('images', [])))
    avg_width = int(results.get('avg_width', 0) or 0)
    avg_height = int(results.get('avg_height', 0) or 0)

    # Fallback: Calculate from files if dimensions are missing
    if (avg_width == 0 or avg_height == 0) and os.path.isdir(folder_path):
        from src.utils.sampling_utils import calculate_folder_dimensions
        calc = calculate_folder_dimensions(folder_path)
        if calc:
            avg_width = int(calc.get('avg_width', 0))
            avg_height = int(calc.get('avg_height', 0))

    extension = "JPG"
    try:
        # Best-effort derive the most common extension from images if present
        exts = []
        for img in results.get('images', []):
            orig = img.get('original_filename') or ''
            if orig:
                _, ext = os.path.splitext(orig)
                if ext:
                    exts.append(ext.upper().lstrip('.'))
        if exts:
            extension = max(set(exts), key=exts.count)
    except Exception:
        pass

    # All-images bbcode (space-separated)
    # Generate per-image BBCode from image_url + thumb_url if not already present
    bbcode_parts = []
    for img in results.get('images', []):
        bb = img.get('bbcode')
        if not bb:
            iu = img.get('image_url', '')
            tu = img.get('thumb_url', '')
            if iu and tu:
                bb = f"[url={iu}][img]{tu}[/img][/url]"
            elif iu:
                bb = f"[url={iu}]{iu}[/url]"
        if bb:
            bbcode_parts.append(bb)
    all_images_bbcode = "  ".join(bbcode_parts)

    # Get file host data from database
    queue_store = None
    try:
        from src.storage.database import QueueStore
        queue_store = QueueStore()
    except Exception as e:
        log(f"Failed to open queue store for artifacts: {e}", level="warning", category="artifact")

    # Get file host download links for BBCode template
    host_links = ''
    if queue_store:
        try:
            from src.utils.template_utils import get_file_host_links_for_template
            host_links = get_file_host_links_for_template(queue_store, folder_path)
        except Exception as e:
            log(f"Failed to get file host links: {e}", level="warning", category="template")

    # Build file_hosts array for JSON artifact
    file_hosts_data = []
    if queue_store:
        try:
            fh_uploads = queue_store.get_file_host_uploads(folder_path)
            for u in fh_uploads:
                if u['status'] == 'completed' and u.get('download_url'):
                    file_hosts_data.append({
                        'host': u['host_name'],
                        'download_url': u['download_url'],
                        'file_id': u.get('file_id', ''),
                        'file_name': u.get('file_name', ''),
                        'md5_hash': u.get('md5_hash', ''),
                        'file_size': u.get('file_size', 0),
                        'deduped': u.get('deduped', False),
                        'part': u.get('part_number', 0) + 1,
                    })
        except Exception as e:
            log(f"Failed to build file_hosts artifact data: {e}", level="warning", category="artifact")

    # Get cover info from results if available (cover_result is a list of per-cover dicts)
    cover_results = results.get('cover_result', []) or []
    c_url = next((r.get('image_url', '') for r in cover_results if r.get('status') == 'success'), '')
    c_thumb = next((r.get('thumb_url', '') for r in cover_results if r.get('status') == 'success'), '')
    if not cover_bbcode:
        cover_bbcode = "\n".join(
            r['bbcode'] for r in cover_results
            if r.get('status') == 'success' and r.get('bbcode')
        )

    template_data = {
        'folder_name': gallery_name,
        'width': avg_width,
        'height': avg_height,
        'longest': max(avg_width, avg_height),
        'extension': extension,
        'picture_count': successful_images,
        'folder_size': f"{total_size / (1024*1024):.1f} MB",
        'gallery_link': results.get('gallery_url', ''),
        'all_images': all_images_bbcode,
        'host_links': host_links,
        'cover': cover_bbcode,
        'cover_url': c_url,
        'cover_thumb_url': c_thumb,
        'custom1': (custom_fields or {}).get('custom1', ''),
        'custom2': (custom_fields or {}).get('custom2', ''),
        'custom3': (custom_fields or {}).get('custom3', ''),
        'custom4': (custom_fields or {}).get('custom4', ''),
        'ext1': (custom_fields or {}).get('ext1', ''),
        'ext2': (custom_fields or {}).get('ext2', ''),
        'ext3': (custom_fields or {}).get('ext3', ''),
        'ext4': (custom_fields or {}).get('ext4', '')
    }
    bbcode_content = generate_bbcode_from_template(template_name, template_data)

    # Compose JSON payload (align with CLI structure)
    json_payload = {
        'meta': {
            'gallery_name': gallery_name,
            'gallery_id': gallery_id,
            'gallery_url': results.get('gallery_url', ''),
            'status': 'completed',
            'started_at': results.get('started_at') or None,
            'finished_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'uploader_version': __version__,
        },
        'settings': {
            'thumbnail_size': results.get('thumbnail_size'),
            'thumbnail_format': results.get('thumbnail_format'),
            'template_name': template_name,
            'parallel_batch_size': results.get('parallel_batch_size'),
        },
        'stats': {
            'total_images': results.get('total_images') or (successful_images + results.get('failed_count', 0)),
            'successful_count': successful_images,
            'failed_count': results.get('failed_count', 0),
            'upload_time': results.get('upload_time', 0),
            'total_size': total_size,
            'uploaded_size': results.get('uploaded_size', 0),
            'avg_width': results.get('avg_width', 0),
            'avg_height': results.get('avg_height', 0),
            'max_width': results.get('max_width', 0),
            'max_height': results.get('max_height', 0),
            'min_width': results.get('min_width', 0),
            'min_height': results.get('min_height', 0),
            'transfer_speed_mb_s': (results.get('transfer_speed', 0) / (1024*1024)) if results.get('transfer_speed', 0) else 0,
        },
        'images': results.get('images', []),
        'cover_result': cover_results,
        'file_hosts': file_hosts_data,
        'failures': [
            {
                'filename': fname,
                'failed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'reason': reason,
            }
            for fname, reason in results.get('failed_details', [])
        ],
        'bbcode_full': bbcode_content,
    }

    written_paths = {}
    # Save BBCode and JSON to .uploaded
    if store_in_uploaded:
        with open(os.path.join(uploaded_subdir, bbcode_filename), 'w', encoding='utf-8') as f:
            f.write(bbcode_content)
        with open(os.path.join(uploaded_subdir, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        written_paths.setdefault('uploaded', {})['bbcode'] = os.path.join(uploaded_subdir, bbcode_filename)
        written_paths.setdefault('uploaded', {})['json'] = os.path.join(uploaded_subdir, json_filename)

    # Save to central location as well
    if store_in_central:
        central_path = get_central_storage_path()
        os.makedirs(central_path, exist_ok=True)
        with open(os.path.join(central_path, bbcode_filename), 'w', encoding='utf-8') as f:
            f.write(bbcode_content)
        with open(os.path.join(central_path, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        written_paths.setdefault('central', {})['bbcode'] = os.path.join(central_path, bbcode_filename)
        written_paths.setdefault('central', {})['json'] = os.path.join(central_path, json_filename)

    return written_paths

def main():
    # Migrate credentials from INI to keyring (runs once, safe to call multiple times)
    migrate_credentials_from_ini()

    # Ensure CSPRNG master key exists — triggers one-time re-encryption migration
    # if upgrading from SHA-256-derived key. Must run after INI migration above.
    try:
        get_encryption_key()
    except CredentialDecryptionError as e:
        log(f"Encryption key initialization failed: {e}", level="error", category="auth")

    # Auto-launch GUI if double-clicked (no arguments, no other console processes)
    if len(sys.argv) == 1:  # No arguments provided
        try:
            # Check if this is the only process attached to the console
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            process_array = (ctypes.c_uint * 1)()
            num_processes = kernel32.GetConsoleProcessList(process_array, 1)
            # If num_processes <= 2, likely double-clicked (only this process and conhost)
            # If num_processes > 2, launched from terminal (cmd.exe/powershell also attached)
            if num_processes <= 2:
                sys.argv.append('--gui')
        except (AttributeError, OSError, TypeError):
            pass  # Not Windows or check failed, don't auto-launch GUI

    # Migrate from old imxup installation if needed (first run after upgrade)
    migrate_from_imxup()

    # Load user defaults
    user_defaults = load_user_defaults()

    parser = argparse.ArgumentParser(description='Upload image folders to imx.to as galleries and generate bbcode.\n\nSettings file: ' + get_config_path())
    parser.add_argument('-v', '--version', action='store_true', help='Show version and exit')
    parser.add_argument('folder_paths', nargs='*', help='Paths to folders containing images')
    parser.add_argument('--name', help='Gallery name (optional, uses folder name if not specified)')
    parser.add_argument('--size', type=int, choices=[1, 2, 3, 4, 6], 
                       default=user_defaults.get('thumbnail_size', 3),
                       help='Thumbnail size: 1=100x100, 2=180x180, 3=250x250, 4=300x300, 6=150x150 (default: 3)')
    parser.add_argument('--format', type=int, choices=[1, 2, 3, 4], 
                       default=user_defaults.get('thumbnail_format', 2),
                       help='Thumbnail format: 1=Fixed width, 2=Proportional, 3=Square, 4=Fixed height (default: 2)')
    parser.add_argument('--max-retries', type=int,
                       default=user_defaults.get('max_retries', 3),
                       help='Maximum retry attempts for failed uploads (default: 3)')
    parser.add_argument('--parallel', type=int,
                       default=user_defaults.get('parallel_batch_size', 4),
                       help='Number of images to upload simultaneously (default: 4)')
    parser.add_argument('--setup-secure', action='store_true',
                       help='Set up secure password storage (interactive)')
    parser.add_argument('--rename-unnamed', action='store_true',
                       help='Rename all unnamed galleries from previous uploads')
    parser.add_argument('--template', '-t', 
                       help='Template name to use for bbcode generation (default: "default")')

    parser.add_argument('--install-context-menu', action='store_true',
                       help='Install Windows context menu integration')
    parser.add_argument('--remove-context-menu', action='store_true',
                       help='Remove Windows context menu integration')
    parser.add_argument('--gui', action='store_true',
                       help='Launch graphical user interface')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode: print all log messages to console')

    args = parser.parse_args()
    if args.version:
        print(f"imxup {__version__}")
        return
    
    # Handle GUI launch
    if args.gui:
        debug_print(f"Launching BBDrop v{__version__} in GUI mode...")
        try:
            # Set environment variable to indicate GUI mode BEFORE stripping --gui from sys.argv
            # This allows ImxToUploader to detect GUI mode even after sys.argv is modified
            os.environ['BBDROP_GUI_MODE'] = '1'

            # Import only lightweight PyQt6 basics for splash screen FIRST
            debug_print("Importing PyQt6.QtWidgets...")
            from PyQt6.QtWidgets import QApplication, QProgressDialog
            from PyQt6.QtCore import Qt, QTimer
            #debug_print("Importing splash screen...")
            from src.gui.splash_screen import SplashScreen

            # Check if folder paths were provided for GUI
            if args.folder_paths:
                # Pass folder paths to GUI for initial loading
                sys.argv = [sys.argv[0]] + args.folder_paths
            else:
                # Remove GUI arg to avoid conflicts with Qt argument parsing
                sys.argv = [sys.argv[0]]

            # Create QApplication and show splash IMMEDIATELY (before heavy imports)
            debug_print("Creating QApplication...")
            app = QApplication(sys.argv)
            app.setApplicationName("BBDrop")
            #debug_print("Setting Fusion style...")
            app.setStyle("Fusion")
            #debug_print("Setting setQuitOnLastWindowClosed to True...")
            app.setQuitOnLastWindowClosed(True)

            # Install Qt message handler to suppress QPainter warnings
            from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
            def qt_message_handler(msg_type, context, message):
                del context  # Required by Qt signature but unused
                # Suppress QPainter warnings - they're handled gracefully in code
                if "QPainter" in message:
                    return
                # Allow other Qt warnings through
                if msg_type == QtMsgType.QtWarningMsg:
                    print(f"Qt Warning: {message}")

            qInstallMessageHandler(qt_message_handler)

            # Install global exception handler for Qt event loop
            debug_print("Installing exception hook...")
            def qt_exception_hook(exctype, value, traceback_obj):
                import traceback as tb_module
                tb_lines = tb_module.format_exception(exctype, value, traceback_obj)
                tb_text = ''.join(tb_lines)
                print(f"\n{'='*60}")
                print("UNCAUGHT EXCEPTION IN QT EVENT LOOP:")
                print(f"{'='*60}")
                print(tb_text)
                print(f"{'='*60}\n")
                # Also try to write to a crash log file
                try:
                    crash_log = os.path.join(os.path.expanduser("~"), ".bbdrop", "crash.log")
                    with open(crash_log, 'a', encoding='utf-8') as f:
                        f.write(f"\n{'='*60}\n")
                        f.write(f"CRASH AT {datetime.now()}\n")
                        f.write(tb_text)
                        f.write(f"{'='*60}\n")
                    print(f"Crash details written to: {crash_log}")
                except Exception:
                    pass

            sys.excepthook = qt_exception_hook
            #debug_print("Exception hook installed")

            debug_print("Creating splash screen...")
            splash = SplashScreen()
            #debug_print("Showing splash screen...")
            splash.show()
            splash.update_status("Starting BBDrop...")
            debug_print("Processing events...")
            app.processEvents()  # Force splash to appear NOW
            #debug_print("Events processed")

            # NOW import the heavy main_window module (while splash is visible)
            splash.set_status("Loading modules")
            debug_print(f"Launching GUI for BBDrop v{__version__}...")
            if sys.stdout is not None:
                try:
                    sys.stdout.flush()
                except (OSError, AttributeError):
                    pass
            debug_print("Importing main_window...")
            from src.gui.main_window import BBDropGUI, check_single_instance

            # Check for existing instance
            folders_to_add = []
            if len(sys.argv) > 1:
                for arg in sys.argv[1:]:
                    if os.path.isdir(arg):
                        folders_to_add.append(arg)
                if folders_to_add and check_single_instance(folders_to_add[0]):
                    splash.finish_and_hide()
                    return
            else:
                if check_single_instance():
                    print(f"{timestamp()} INFO: BBDrop GUI already running, bringing existing instance to front.")
                    splash.finish_and_hide()
                    return

            splash.set_status("Creating main window")

            # Create main window (pass splash for progress updates)
            window = BBDropGUI(splash)

            # Now set Fusion style after widgets are initialized
            splash.set_status("Setting Fusion style...")
            app.setStyle("Fusion")

            # Add folders from command line if provided
            if folders_to_add:
                window.add_folders(folders_to_add)

            # Hide splash BEFORE loading galleries
            splash.finish_and_hide()

            # Get gallery count to set up progress dialog properly
            gallery_count = len(window.queue_manager.get_all_items())

            # Load saved galleries with progress dialog (window exists but not shown yet)
            debug_print(f"Loading {gallery_count} galleries with progress dialog")
            progress = QProgressDialog("Loading saved galleries...", None, 0, gallery_count, None)
            progress.setWindowTitle("BBDrop")
            progress.setWindowModality(Qt.WindowModality.ApplicationModal)
            progress.setMinimumDuration(0)  # Show immediately
            progress.show()
            QApplication.processEvents()

            # Progress callback to update dialog with count
            def update_progress(current, total):
                progress.setValue(current)
                progress.setLabelText(f"{current}/{total} galleries loaded")
                # Process events to keep UI responsive (already batched every 10 galleries)
                QApplication.processEvents()

            window._initialize_table_from_queue(progress_callback=update_progress)

            # DO NOT call processEvents() here - it would force immediate execution of the
            # QTimer.singleShot(100, _create_deferred_widgets) callback, creating 997 widgets
            # synchronously and blocking the UI for 10+ seconds BEFORE the window is shown.
            # Let the deferred widget creation happen naturally after window.show().

            progress.close()

            # NOW show the main window (galleries already loaded)
            window.show()
            window.raise_()        # Bring to front of window stack

            # Defer window activation to avoid blocking the event loop
            QTimer.singleShot(0, window.activateWindow)

            # Initialize file host workers AFTER GUI is loaded and displayed
            if hasattr(window, "file_host_manager") and window.file_host_manager:
                # Count enabled hosts BEFORE starting them (read from INI directly)
                from src.core.file_host_config import get_config_manager, get_file_host_setting
                config_manager = get_config_manager()
                enabled_count = 0
                for host_id in config_manager.hosts:
                    if get_file_host_setting(host_id, 'enabled', 'bool'):
                        enabled_count += 1

                window._file_host_startup_expected = enabled_count
                if window._file_host_startup_expected == 0:
                    window._file_host_startup_complete = True
                    log("No file host workers enabled, skipping startup tracking", level="debug", category="startup")
                else:
                    log(f"Waiting for {window._file_host_startup_expected} file host worker{'s' if window._file_host_startup_expected != 1 else ''}",
                        level="debug", category="startup")

                # Now start the workers
                QTimer.singleShot(100, lambda: window.file_host_manager.init_enabled_hosts())

            # Now that GUI is visible, hide the console window (unless --debug)
            if os.name == 'nt' and '--debug' not in sys.argv:
                try:
                    import ctypes
                    kernel32 = ctypes.WinDLL('kernel32')
                    user32 = ctypes.WinDLL('user32')
                    console_window = kernel32.GetConsoleWindow()
                    if console_window:
                        # Try multiple methods to hide the console
                        user32.ShowWindow(console_window, 0)  # SW_HIDE
                        # Also try moving it off-screen
                        user32.SetWindowPos(console_window, 0, -32000, -32000, 0, 0, 0x0001)  # SWP_NOSIZE
                except (AttributeError, OSError):
                    pass

            sys.exit(app.exec())

        except ImportError as e:
            debug_print(f"CRITICAL: Import error: {e}")
            sys.exit(1)
        except Exception as e:
            debug_print(f"CRITICAL: Error launching GUI: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # Handle secure setup
    if args.setup_secure:
            if setup_secure_password():
                debug_print("Setup complete! You can now use the script without storing passwords in plaintext.")
            else:
                debug_print("ERROR: Setup failed. Please try again.")
            return
    
    # Handle context menu installation
    if args.install_context_menu:
        if create_windows_context_menu():
            debug_print("Context Menu: Installed successfully")
        else:
            debug_print("Context Menu: ERROR: Failed to install context menu.")
        return
    
    # Handle context menu removal
    if args.remove_context_menu:
        if remove_windows_context_menu():
            debug_print("Context Menu: Removed successfully")
        else:
            debug_print("Context Menu: Failed to removeFailed to remove context menu.")
        return
    
    # Handle gallery visibility changes
    if len(args.folder_paths) == 1 and args.folder_paths[0].startswith('--'):
        # This is a gallery ID for visibility change
        gallery_id = args.folder_paths[0][2:]  # Remove -- prefix
        
        uploader = ImxToUploader()
        
        if args.public:
            if uploader.set_gallery_visibility(gallery_id, 1):
                debug_print(f"Gallery {gallery_id} set to public")
            else:
                debug_print(f"ERROR: Failed to set gallery {gallery_id} to public")
        elif args.private:
            if uploader.set_gallery_visibility(gallery_id, 0):
                debug_print(f"Gallery {gallery_id} set to private")
            else:
                debug_print(f"ERROR: Failed to set gallery {gallery_id} to private")
        else:
            debug_print(f"{timestamp()} WARNING: Please specify --public or --private")
        return
    
    # Handle unnamed gallery renaming
    if args.rename_unnamed:
        unnamed_galleries = get_unnamed_galleries()

        if not unnamed_galleries:
            #log(f" No unnamed galleries found to rename")
            return

        debug_print(f"Found {len(unnamed_galleries)} unnamed galleries to rename:")
        for gallery_id, intended_name in unnamed_galleries.items():
            debug_print(f"   {gallery_id} -> '{intended_name}'")

        # Use RenameWorker for all web-based rename operations
        try:
            from src.processing.rename_worker import RenameWorker
            rename_worker = RenameWorker()

            # Wait for initial login (RenameWorker logs in automatically on init)
            import time
            if not rename_worker.login_complete.wait(timeout=30):
                debug_print("RenameWorker: Login timeout")
                debug_print(" To rename galleries manually:")
                debug_print(" 1. Log in to https://imx.to in your browser")
                debug_print(" 2. Navigate to each gallery and rename it manually")
                debug_print(f" Gallery IDs to rename: {', '.join(unnamed_galleries.keys())}")
                return 1

            if not rename_worker.login_successful:
                debug_print("RenameWorker: Login failed")
                debug_print(" DDoS-Guard protection may be blocking automated login.")
                debug_print(" To rename galleries manually:")
                debug_print(" 1. Log in to https://imx.to in your browser")
                debug_print(" 2. Navigate to each gallery and rename it manually")
                debug_print(" 3. Or export cookies from browser and place in cookies.txt file")
                debug_print(f" Gallery IDs to rename: {', '.join(unnamed_galleries.keys())}")
                return 1

            # Queue all renames
            for gallery_id, intended_name in unnamed_galleries.items():
                rename_worker.queue_rename(gallery_id, intended_name)

            # Wait for all renames to complete
            debug_print(f"Processing {len(unnamed_galleries)} rename requests...")
            while rename_worker.queue_size() > 0:
                time.sleep(0.1)

            # Count successes by checking which galleries are still in unnamed list
            remaining_unnamed = get_unnamed_galleries()
            success_count = len(unnamed_galleries) - len(remaining_unnamed)

            debug_print(f"Successfully renamed {success_count}/{len(unnamed_galleries)} galleries")

            # Cleanup
            rename_worker.stop()

            return 0 if success_count == len(unnamed_galleries) else 1

        except Exception as e:
            debug_print(f"Failed to initialize RenameWorker: {e}")
            return 1
    
    # Check if folder paths are provided (required for upload)
    if not args.folder_paths:
        parser.print_help()
        return 0
    
    # Expand wildcards in folder paths
    expanded_paths = []
    for path in args.folder_paths:
        if '*' in path or '?' in path:
            # Expand wildcards
            expanded = glob.glob(path)
            if not expanded:
                debug_print(f"Warning: No folders found matching pattern: {path}")
            expanded_paths.extend(expanded)
        else:
            expanded_paths.append(path)
    
    if not expanded_paths:
        debug_print("No valid folders found to upload.")
        return 1  # No valid folders
    
    # Determine public gallery setting
    # public_gallery is deprecated but kept for compatibility
    # All galleries are public now
    
    try:
        uploader = ImxToUploader()
        all_results = []

        # ImxToUploader is now API-only (no web login needed)
        # RenameWorker handles all web operations and logs in automatically

        # Use shared UploadEngine for consistent behavior
        from src.core.engine import UploadEngine
        
        # Create RenameWorker for background renaming
        rename_worker = None
        try:
            from src.processing.rename_worker import RenameWorker
            rename_worker = RenameWorker()
            debug_print("Rename Worker: Background worker initialized")
        except Exception as e:
            debug_print(f"Rename Worker: Error trying to initialize RenameWorker: {e}")
            
        engine = UploadEngine(uploader, rename_worker)

        # Process multiple galleries
        for folder_path in expanded_paths:
            gallery_name = args.name if args.name else None

            try:
                debug_print(f"Starting upload: {os.path.basename(folder_path)}")
                results = engine.run(
                    folder_path=folder_path,
                    gallery_name=gallery_name,
                    thumbnail_size=args.size,
                    thumbnail_format=args.format,
                    max_retries=args.max_retries,
                    parallel_batch_size=args.parallel,
                    template_name=args.template or "default",
                )

                # Save artifacts through shared helper
                try:
                    save_gallery_artifacts(
                        folder_path=folder_path,
                        results=results,
                        template_name=args.template or "default",
                    )
                except Exception as e:
                    debug_print(f"WARNING: Artifact save error: {e}")

                all_results.append(results)

            except KeyboardInterrupt:
                debug_print(f"{timestamp()} Upload interrupted by user")
                # Cleanup RenameWorker on interrupt
                if rename_worker:
                    rename_worker.stop()
                    debug_print("Background RenameWorker stopped")
                break
            except Exception as e:
                debug_print(f"Error uploading {folder_path}: {str(e)}")
                continue
        
        # Display summary for all galleries
        if all_results:
            print("\n" + "="*60)
            print("UPLOAD SUMMARY")
            print("="*60)
            
            total_images = sum(len(r['images']) for r in all_results)
            total_time = sum(r['upload_time'] for r in all_results)
            total_size = sum(r['total_size'] for r in all_results)
            total_uploaded = sum(r['uploaded_size'] for r in all_results)
            
            print(f"Total galleries: {len(all_results)}")
            print(f"Total images: {total_images}")
            print(f"Total time: {total_time:.1f} seconds")
            try:
                total_size_str = format_binary_size(total_size, precision=1)
            except Exception:
                total_size_str = f"{int(total_size)} B"
            print(f"Total size: {total_size_str}")
            if total_time > 0:
                try:
                    avg_kib_s = (total_uploaded / total_time) / 1024.0
                    avg_speed_str = format_binary_rate(avg_kib_s, precision=1)
                except Exception:
                    avg_speed_str = f"{(total_uploaded / total_time) / 1024.0:.1f} KiB/s"
                print(f"Average speed: {avg_speed_str}")
            else:
                print("Average speed: 0 KiB/s")
            
            for i, results in enumerate(all_results, 1):
                total_attempted = results['successful_count'] + results['failed_count']
                print(f"\nGallery {i}: {results['gallery_name']}")
                print(f"  URL: {results['gallery_url']}")
                print(f"  Images: {results['successful_count']}/{total_attempted}")
                print(f"  Time: {results['upload_time']:.1f}s")
                try:
                    size_str = format_binary_size(results['uploaded_size'], precision=1)
                except Exception:
                    size_str = f"{int(results['uploaded_size'])} B"
                print(f"  Size: {size_str}")
                try:
                    kib_s = (results['transfer_speed'] or 0) / 1024.0
                    speed_str = format_binary_rate(kib_s, precision=1)
                except Exception:
                    speed_str = f"{((results['transfer_speed'] or 0) / 1024.0):.1f} KiB/s"
                print(f"  Speed: {speed_str}")
            
            # Cleanup RenameWorker
            if rename_worker:
                rename_worker.stop()
                debug_print("Rename Worker: Background worker stopped")
                
            return 0  # Success
        else:
            # Cleanup RenameWorker
            if rename_worker:
                rename_worker.stop()
                debug_print("Background RenameWorker stopped")
                
            debug_print(f"{timestamp()} No galleries were successfully uploaded.")
            return 1  # No galleries uploaded
            
    except Exception as e:
        # Cleanup RenameWorker on exception
        try:
            if 'rename_worker' in locals() and rename_worker:
                rename_worker.stop()
                debug_print(f"ERROR: Rename Worker: Error: Background worker stopped on exception: {e}")
        except Exception:
            pass  # Ignore cleanup errors
        debug_print(f"ERROR: Rename Worker: Error: {str(e)}")
        return 1  # Error occurred

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("KeyboardInterrupt: Exiting gracefully...", level="debug", category="ui")
        sys.exit(0)
    except SystemExit:
        # Handle argparse errors gracefully
        pass
    except Exception as e:
        # Log crash to file when running with --noconsole (so we can debug it)
        try:
            import traceback
            with open('bbdrop_crash.log', 'w') as f:
                f.write("BBDrop crashed:\n")
                f.write(f"{traceback.format_exc()}\n")
        except (OSError, IOError):
            pass
        # Also try to log it normally
        try:
            log(f"CRITICAL: Fatal Error: {e}", level="critical", category="ui")
        except Exception:
            pass
        sys.exit(1)
