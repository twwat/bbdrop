# Installation

BBDrop runs on Windows, macOS, and Linux. Download the latest release from [GitHub Releases](https://github.com/twwat/bbdrop/releases/latest).

## Windows

**Installer (recommended):** Download `bbdrop-x.x.x-windows-x64-setup.exe` and run it. Alternatively, download the `.msi` installer if your organization prefers MSI packages.

**Portable:** Download `bbdrop-x.x.x-windows-x64-portable.zip`, extract it anywhere, and run `bbdrop.exe`. Settings are stored alongside the executable, making it easy to run from a USB drive.

## macOS

**DMG (recommended):** Download the `.dmg` for your architecture:

- **Apple Silicon (M1/M2/M3):** `bbdrop-x.x.x-macos-arm64.dmg`
- **Intel:** `bbdrop-x.x.x-macos-x64.dmg`

Open the DMG and drag BBDrop to your Applications folder.

**Portable:** Download the corresponding `.tar.gz`, extract it, and run directly.

## Linux

**AppImage (recommended):** Download `bbdrop-x.x.x-linux-x64.AppImage`, make it executable (`chmod +x`), and run it. Works on most distributions without installation.

**Debian/Ubuntu:** Download the `.deb` package and install with:

```bash
sudo dpkg -i bbdrop-x.x.x-linux-x64.deb
```

**Fedora/RHEL:** Download the `.rpm` package and install with:

```bash
sudo rpm -i bbdrop-x.x.x-linux-x64.rpm
```

**Portable:** Download the `.tar.gz`, extract it, and run the `bbdrop` binary.

## First Launch

When you first open BBDrop, you'll see the main window with an empty gallery queue on the left and the host panel on the right. No hosts are enabled by default — head to [Your First Upload](first-upload.md) to get started.

!!! tip
    The portable versions store settings alongside the executable, making them ideal for USB drives or keeping separate configurations.
