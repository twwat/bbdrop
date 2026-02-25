# Using the Interface

A quick tour of the BBDrop window and its features.

---

## Main Window

### Queue Table (Center)

Shows all your galleries with status, progress, and settings. Right-click any gallery for actions like Copy BBCode, Retry, Move to Tab, or Remove.

Key columns: Name, Status, Progress, Images, Size, Template, Image Host. Right-click the column header to show/hide over 25 available columns including custom fields, file host status, and online status.

### Toolbar (Top)

| Button | What It Does |
|--------|--------------|
| **Add Folder** | Browse for folders to add |
| **Start** | Begin uploading all ready galleries |
| **Pause** | Pause all active uploads |
| **Clear Completed** | Remove finished galleries from the queue |
| **Settings** | Open the settings dialog |

### Quick Settings (Right Panel)

Thumbnail size, template selection, image host selector, and shortcut buttons for host configuration, templates, and link scanning.

### Upload Workers (Right Panel)

Shows all available image and file hosts with their status. Right-click a host to enable, disable, or configure it. Double-click to open its configuration dialog.

### Log Panel (Bottom Right)

Real-time upload messages. Filter by category or severity in **Settings > Logs**.

### Tabs (Bottom)

Organize galleries into groups. Right-click the tab bar to create new tabs. Ctrl+T to create, Ctrl+W to close, double-click to rename.

---

## Gallery Status

| Status | Meaning |
|--------|---------|
| **Ready** | Scanned and ready to upload |
| **Uploading** | Currently uploading |
| **Paused** | Paused by you |
| **Completed** | Upload finished successfully |
| **Failed** | Upload failed — check the status column for the error |
| **Incomplete** | Some images uploaded, others failed |

---

## Adding Galleries

- **Drag and drop** folders or archives (ZIP, RAR, 7Z) onto the queue
- Click **Add Folder** in the toolbar
- Use the Windows Explorer right-click menu (if installed via Settings)

Multiple folders can be added at once. Archives are automatically extracted.

---

## Settings Dialog

Click **Settings** in the toolbar to open the settings dialog. Settings are organized in a sidebar:

| Section | What You'll Find |
|---------|------------------|
| **General** | Storage location, auto-start/clear, appearance (theme, font size) |
| **Image Hosts** | IMX.to and TurboImageHost — credentials, thumbnails, connection settings |
| **File Hosts** | 7 file hosts — credentials, storage monitoring, auto-upload triggers |
| **Templates** | Create and edit BBCode templates |
| **Image Scan** | Corruption checking, dimension sampling, exclusion patterns |
| **Covers** | Cover photo detection rules and upload settings |
| **Hooks** | External program hooks for gallery lifecycle events |
| **Proxy** | Proxy pools, per-host proxy assignment, Tor support |
| **Logs** | GUI and file log verbosity, retention, categories |
| **Notifications** | Per-event audio and toast notification settings |
| **Archive** | Archive format (ZIP/7Z), compression, split settings |
| **Advanced** | Power-user settings in a searchable table |

!!! tip
    Most settings have **tooltips** — hover over any setting to see a description. Some settings also have **info buttons** (ℹ) with additional context, and text fields include **placeholder text** showing expected formats or example values.

---

## Notifications

BBDrop can alert you with sound and/or toast messages when key events happen. Configure per-event settings in **Settings > Notifications**.

| Event | Default |
|---|---|
| Queue finished (all galleries done) | Sound + toast |
| Gallery failed | Sound + toast |
| File host upload failed | Sound + toast |
| Low disk space warning | Sound + toast |
| Gallery completed | Off |
| File host upload completed | Off |
| File host spin-up complete | Off |

Each event can have sound, toast, or both toggled independently. Click the browse button next to any event to select a custom WAV file.

Toast notifications appear from the system tray icon.

---

## Disk Space Monitoring

BBDrop monitors free disk space on the drives used for its database and temporary archives.

| Level | Threshold | What Happens |
|---|---|---|
| Warning | < 2 GB free | Status bar warning, notification |
| Critical | < 512 MB free | New uploads blocked |
| Emergency | < 100 MB free | Aggressive alerts, reserve file released |

Thresholds are configurable in **Settings > Advanced**. Polling frequency increases automatically as free space decreases.

---

## Statistics

Open **Tools > Statistics** to see upload metrics:

- **General tab** — session duration, total galleries/images/bytes uploaded, average and peak speed, per-host image counts
- **File Hosts tab** — per-host upload counts, success/failure breakdown, download link counts

---

## System Tray

BBDrop minimizes to the system tray. Right-click the tray icon for quick actions. Toast notifications appear from the tray icon when enabled.

The app keeps running in the background when minimized — uploads continue uninterrupted.

---

## Tips

- **Theme toggle** — switch between dark and light modes in **Settings > General**
- **Archives** — drop ZIP, RAR, or 7Z files just like folders
- **Single instance** — opening BBDrop again adds galleries to the existing window instead of launching a second copy
- **Keyboard shortcuts** — press **Ctrl+.** to see all available shortcuts, or see [Keyboard Shortcuts](../getting-started/keyboard-shortcuts.md)

---

See [Queue Management](queue-management.md) for detailed queue operations and context menu actions.
