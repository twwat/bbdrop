#!/usr/bin/env python3
"""
Simple launcher for the IMX.to GUI uploader
Fast startup: shows splash BEFORE heavy imports
"""

import sys
import os

# Add project root to path to find imxup module (handles both frozen and unfrozen)
if getattr(sys, 'frozen', False):
    # Running as frozen executable - PyInstaller handles imports, no need to modify sys.path
    pass
else:
    # Running as Python script - add project root to sys.path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Main launcher - shows splash FIRST, then loads heavy modules"""
    # Install exception hook BEFORE anything else
    try:
        from src.utils.logger import install_exception_hook
        install_exception_hook()
    except Exception:
        pass

    # Import only lightweight PyQt6 basics for splash
    try:
        from PyQt6.QtWidgets import QApplication
        from src.gui.splash_screen import SplashScreen
    except ImportError as e:
        print("Error: PyQt6 is required for GUI mode.")
        print("Install with: pip install PyQt6")
        print(f"Import error: {e}")
        sys.exit(1)

    # Create QApplication and show splash IMMEDIATELY
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    splash = SplashScreen()
    splash.show()
    splash.update_status("Starting ImxUp...")
    app.processEvents()  # Force splash to appear NOW

    # NOW import the heavy stuff (while splash is visible)
    try:
        splash.set_status("Loading modules")
        from src.gui.main_window import ImxUploadGUI, check_single_instance

        # Handle command line arguments
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
                print("ImxUp GUI already running, bringing existing instance to front.")
                splash.finish_and_hide()
                return

        splash.set_status("Creating main window")

        # Create main window (pass splash for progress updates)
        window = ImxUploadGUI(splash)

        # Add folders from command line if provided
        if folders_to_add:
            window.add_folders(folders_to_add)

        # Hide splash and show main window
        splash.finish_and_hide()
        window.show()

        sys.exit(app.exec())

    except Exception as e:
        splash.finish_and_hide()
        print(f"Error launching GUI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()