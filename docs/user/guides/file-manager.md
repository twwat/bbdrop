# File Manager

The file manager lets you browse and manage files stored on your remote file hosts without leaving BBDrop. It's accessible from **Tools > File Manager**, or via the **File Manager** button in the quick settings panel.

The dialog is non-modal — you can keep it open while uploads are running.

---

## Opening the File Manager

- **Tools > File Manager** in the menu bar
- **File Manager** button in the quick settings panel

Use the host dropdown at the top of the dialog to switch between hosts. The folder tree on the left and the file list on the right update automatically.

---

## Navigation

- Click a folder in the tree to browse it
- Double-click a folder in the file list to enter it
- **Backspace** — navigate back
- **Alt+Up** — go to parent folder
- **F5** — refresh the current folder

Folder listings are cached for 60 seconds. Press F5 to force a refresh.

---

## Operations

Not all operations are available on every host. The toolbar and context menu show only what the current host supports.

| Operation | K2S / TezFiles / FileBoom | RapidGator | Katfile | Filespace | Filedot |
|---|---|---|---|---|---|
| Browse files | Yes | Yes | Yes | Yes | Yes (scraping) |
| Create folder | Yes | Yes | Yes | Yes | — |
| Rename | Yes | Yes | Yes | Yes | — |
| Move | Yes (batch) | Yes | Yes | Yes | — |
| Copy | — | Yes | Clone | Clone | — |
| Delete | Yes | Yes | Yes | Yes | Yes |
| Trash / restore | — | Yes | — | — | — |
| Remote URL upload | Yes | Yes | — | — | — |
| File properties | — | — | — | — | Yes |

### Rename

Select a file or folder and press **F2**, or right-click and choose **Rename**. Enter the new name and press Enter.

### Move

Select one or more files, then drag them to the destination folder in the tree, or use **right-click > Move to...**.

### Copy / Clone

On RapidGator, copy creates a true duplicate. On Katfile and Filespace, the clone operation creates a reference to the same underlying file rather than duplicating storage.

### Delete

Select files and press **Delete**, or right-click and choose **Delete**. On RapidGator, deleted files go to the trash and can be restored. On all other hosts, deletion is permanent.

### Remote Upload (K2S family and RapidGator)

Use **right-click > Upload from URL** to submit a URL for the host to fetch directly — no local download required. A progress indicator polls for completion.

### File Properties (Filedot)

Right-click a file and choose **Properties** to view and edit extended metadata including title, description, and content flags. When multiple files are selected, the diff view highlights fields that differ across the selection.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Delete | Remove selected files or folders |
| F2 | Rename selected file or folder |
| F5 | Refresh current folder |
| Ctrl+C | Copy download link |
| Backspace | Navigate back |
| Alt+Up | Go to parent folder |

---

## Authentication

The file manager uses the same credentials as the upload workers. No separate login is needed — if a host is authenticated for uploads, it's authenticated here too.

| Host | Auth Method |
|---|---|
| K2S / TezFiles / FileBoom | API key |
| RapidGator | Token login (cached 24 h, refreshed automatically) |
| Katfile | API key |
| Filespace | API key for browsing; session cookie for delete |
| Filedot | Session cookie (web scraping) |

---

## Tips

- The file manager opens without blocking the main window — uploads keep running while you browse
- On Filedot, folder navigation is not supported; all files appear in a flat list
- RapidGator's trash is the only host with a recoverable delete — use it before removing files you might need back
