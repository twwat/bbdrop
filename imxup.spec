# -*- mode: python ; coding: utf-8 -*-

# Build both GUI (no console) and CLI (with console) executables from same codebase

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs
import os
import sys
import subprocess
import glob

# Collect all pycurl dependencies (including DLLs on Windows)
pycurl_datas, pycurl_binaries, pycurl_hiddenimports = collect_all('pycurl')

print(f"\n=== PyInstaller pycurl Debug Info ===")
print(f"Platform: {sys.platform}")
print(f"pycurl_binaries from collect_all: {pycurl_binaries}")
print(f"pycurl_datas from collect_all: {pycurl_datas}")
print(f"pycurl_hiddenimports: {pycurl_hiddenimports}")

# Platform-specific binary collection
additional_binaries = []

if sys.platform == 'win32':
    # Windows: pycurl uses delvewheel - DLLs have HASHED names in site-packages ROOT
    try:
        import pycurl
        pycurl_file = pycurl.__file__
        print(f"pycurl.__file__ (Windows): {pycurl_file}")

        # Get site-packages directory (parent of pycurl)
        site_packages = os.path.dirname(pycurl_file)
        print(f"site-packages directory: {site_packages}")

        # Find pycurl .pyd file (e.g., pycurl.cp314-win_amd64.pyd)
        pyd_pattern = 'pycurl*.pyd'
        pyd_files = glob.glob(os.path.join(site_packages, pyd_pattern))
        for pyd_file in pyd_files:
            additional_binaries.append((pyd_file, '.'))
            print(f"✓ Found .pyd: {os.path.basename(pyd_file)}")

        # Find delvewheel DLLs with HASHED names in site-packages root
        # Pattern: libcurl-[hash].dll, libssl-3-x64-[hash].dll, etc.
        dll_patterns = [
            'libcurl-*.dll',          # libcurl-14abb589ef9dfe0c739cf0592f05f654.dll
            'libssl-*.dll',           # libssl-3-x64-699b7bb76547175d6ab5d01a25560bd7.dll
            'libcrypto-*.dll',        # libcrypto-3-x64-f785dee607a120f481756c290b2586cf.dll
            'libssh2-*.dll',
            'nghttp2-*.dll',
            'libbrotli*.dll',
            'zlib-*.dll'
        ]

        for pattern in dll_patterns:
            dll_files = glob.glob(os.path.join(site_packages, pattern))
            for dll_file in dll_files:
                additional_binaries.append((dll_file, '.'))
                print(f"✓ Found .dll: {os.path.basename(dll_file)}")

        if not pyd_files:
            print(f"⚠ WARNING: No pycurl .pyd file found in {site_packages}")
            print(f"⚠ Run: python find_pycurl.py to diagnose")

    except Exception as e:
        print(f"⚠ Warning: Could not locate pycurl DLLs: {e}")
        import traceback
        traceback.print_exc()

elif sys.platform.startswith('linux'):
    # Linux: pycurl is typically a .so file with libcurl dependency
    try:
        import pycurl
        pycurl_path = pycurl.__file__
        pycurl_dir = os.path.dirname(pycurl_path)

        print(f"pycurl path (Linux): {pycurl_path}")
        print(f"pycurl directory: {pycurl_dir}")

        # Add pycurl.so itself if not already in binaries
        if os.path.exists(pycurl_path) and pycurl_path.endswith('.so'):
            # Check if already in pycurl_binaries
            if not any(pycurl_path in str(b) for b in pycurl_binaries):
                additional_binaries.append((pycurl_path, '.'))
                print(f"✓ Added pycurl.so: {pycurl_path}")
            else:
                print(f"✓ pycurl.so already in binaries")

        # Find libcurl dependencies using ldd
        try:
            ldd_output = subprocess.check_output(['ldd', pycurl_path], text=True)
            print(f"\nldd output for pycurl:\n{ldd_output}")

            # Parse ldd output for libcurl
            for line in ldd_output.split('\n'):
                if 'libcurl' in line:
                    parts = line.split('=>')
                    if len(parts) > 1:
                        lib_path = parts[1].split('(')[0].strip()
                        if os.path.exists(lib_path):
                            additional_binaries.append((lib_path, '.'))
                            print(f"✓ Added libcurl dependency: {lib_path}")
        except subprocess.CalledProcessError as e:
            print(f"⚠ Warning: ldd failed: {e}")

            # Fallback: common libcurl locations on Linux
            common_paths = [
                '/lib/x86_64-linux-gnu/libcurl-gnutls.so.4',
                '/usr/lib/x86_64-linux-gnu/libcurl-gnutls.so.4',
                '/lib/x86_64-linux-gnu/libcurl.so.4',
                '/usr/lib/x86_64-linux-gnu/libcurl.so.4',
            ]
            for lib_path in common_paths:
                if os.path.exists(lib_path):
                    additional_binaries.append((lib_path, '.'))
                    print(f"✓ Added libcurl (fallback): {lib_path}")
                    break

    except Exception as e:
        print(f"⚠ Warning: Could not locate pycurl on Linux: {e}")

# Combine all binaries
all_binaries = pycurl_binaries + additional_binaries
print(f"\nTotal binaries for pycurl: {len(all_binaries)}")
for binary in all_binaries:
    print(f"  - {binary}")
print("=" * 50 + "\n")

a = Analysis(
    ['imxup.py'],
    pathex=[],
    binaries=all_binaries,
    datas=pycurl_datas,
    hiddenimports=['imghdr', 'requests', 'PyQt6', 'pycurl', 'certifi'] + pycurl_hiddenimports,
    hookspath=['hooks'],  # Use custom hooks directory
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Primary GUI executable (no console) - for end users
exe_gui = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='imxup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['imxup.ico'],
)

# CLI executable (with console) - for command-line usage and debugging GUI
exe_cli = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='imxup-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['imxup.ico'],
)
