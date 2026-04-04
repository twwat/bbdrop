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
    migrate_plaintext_usernames,
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


# Imports used by main() CLI flow
from src.utils.templates import save_gallery_artifacts
from src.storage.gallery_management import get_unnamed_galleries
from src.utils.windows_integration import create_windows_context_menu, remove_windows_context_menu

def main():
    # Migrate credentials from INI to keyring (runs once, safe to call multiple times)
    migrate_credentials_from_ini()
    migrate_plaintext_usernames()

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
