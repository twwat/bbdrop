# Queue Management

The main table is your gallery queue — every row is a gallery with its status, progress, and settings. This guide covers all the ways to work with it.

## Adding Galleries

**Drag and drop** folders from your file manager into the gallery table. You can also drag archives (ZIP, RAR, 7Z) — BBDrop extracts them and queues the contents.

Other ways to add galleries:

- **File > Add Folders** — browse for one or more folders
- **Windows Explorer right-click** — if you've installed the context menu integration (Settings > Tools > Windows Explorer Integration)

Newly added galleries are scanned automatically to count images and calculate dimensions.

!!! tip
    You can add multiple folders at once — either drag them all in together, or select multiple folders in the Add Folders dialog.

## Tabs

Organize galleries into tabs for different projects or categories:

- **Ctrl+T** — Create a new tab
- **Ctrl+W** — Close the current tab (the Main tab can't be closed)
- **Ctrl+Tab / Ctrl+Shift+Tab** — Switch between tabs
- **Double-click** a tab to rename it
- **Right-click** a gallery and use **Move to tab...** to move it

The **All Tabs** view shows every gallery regardless of which tab it belongs to.

## Columns

Right-click the column header to show or hide columns. Over 25 columns are available:

**Core columns:** #, gallery name, uploaded, progress, status, status text, added, finished, action, size, transfer, renamed, template, image host, gallery_id

**Custom fields:** Custom1-4 (user-defined), ext1-4 (from hooks)

**Other:** file hosts, hosts action, online status

Columns can be reordered by dragging the headers. The Upload Workers table on the right also has configurable columns with nested metrics (bytes uploaded, files, speed, success rate — each trackable per session, today, or all-time).

## Inline Editing

Click directly on editable cells in the table to modify them:

- **Gallery name** — Click to rename
- **Template** — Click to select from dropdown
- **Image host** — Click to select from dropdown
- **Custom1-4** — Click to enter freeform text

Press **Enter** to save and move to the next row. Press **Escape** to cancel.

## Context Menu

Right-click selected galleries for all available actions:

### Upload Actions
- **Start Selected** — Begin uploading
- **Cancel Upload** — Cancel a queued or in-progress upload
- **Retry Upload** — Retry a failed upload

### File Actions
- **Open Folder** — Open the gallery folder in your file manager
- **Manage Files** — Open file management dialog
- **Rename Gallery** — Change the gallery name

### Scanning
- **Rescan for New Images** — Look for images added to the folder since the last scan (preserves existing uploads)
- **Rescan All Items** — Full rescan of the gallery
- **Reset Gallery** — Completely reset and rescan from scratch

### Completed Gallery Actions
- **View BBCode** — Preview the generated BBCode
- **Copy BBCode** — Copy to clipboard (Ctrl+C also works)
- **Regenerate BBCode** — Re-generate from current template
- **Open Gallery Link** — Open the gallery URL in your browser
- **Check Online Status** — Verify images are still accessible

### Bulk Actions
- **Set template to...** — Change template for all selected galleries
- **Set image host to...** — Change image host for all selected galleries
- **Move to tab...** — Move selected galleries to a different tab
- **Delete Selected** — Remove from queue

## Queue Controls

- **Start** toolbar button — Start all queued galleries
- **Pause** — Pause active uploads
- **Clear Completed** — Remove completed galleries from the queue
- **Start uploads automatically** — Checkbox in Quick Settings to auto-start when scanning completes

## Keyboard Shortcuts

| Key | Action |
|---|---|
| Delete | Remove selected galleries |
| Ctrl+C | Copy BBCode for selected galleries |
| F2 | Rename selected gallery |
| Home | Jump to first gallery |
| End | Jump to last gallery |
| Enter | Save inline edit and move to next row |
