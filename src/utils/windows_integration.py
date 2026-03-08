"""Windows context menu integration (registry-based)."""

import sys
import os
import platform

try:
    import winreg  # Windows-only
except ImportError:
    winreg = None  # Not available on Linux/Mac

from src.utils.logger import log
from src.utils.paths import get_project_root


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
