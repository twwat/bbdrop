# Image Scanning & Link Checking

BBDrop has two scanning features: pre-upload image scanning (validates images before upload) and the link scanner (checks if uploaded galleries are still online).

## Image Scanning

When you add a gallery to the queue, BBDrop automatically scans the images to validate them and calculate dimensions. This data feeds into template placeholders like `#width#`, `#height#`, and `#pictureCount#`.

### How It Works

1. Images are checked for corruption using fast detection (imghdr library with PIL fallback)
2. A sample of images is opened to calculate average dimensions
3. Corrupt or invalid files are excluded from the upload

### Settings

Configure scanning behavior in **Settings > Image Scan**:

**Corruption checking:**

- **Use fast corruption checking** — Enabled by default. Uses imghdr for quick validation, falling back to PIL for uncertain files.

**Dimension sampling** — Instead of opening every image (slow for large galleries), BBDrop samples a subset:

- **Fixed count** — Sample a set number of images (default: 25)
- **Percentage** — Sample a percentage of all images (default: 10%)

**Exclusions** — Skip certain images from the dimension sample:

- **Skip first image** — Often a cover or poster
- **Skip last image** — Often credits or a logo
- **Skip images smaller than X%** — Exclude images below a size threshold relative to the largest image (filters out thumbnails and previews)
- **Skip filename patterns** — Comma-separated wildcards (e.g., `cover*, thumb*, poster*`)

**Statistics:**

- **Exclude outliers** — Remove images outside 1.5x the interquartile range
- **Average method** — Mean (arithmetic average) or Median (default, more robust to outliers)

## Link Scanner

The link scanner checks whether your uploaded galleries and images are still accessible online.

### Opening the Scanner

Click the **Link Scan** button in the quick settings panel to open the Link Scanner Dashboard.

### Status Overview

The dashboard shows counts for:

- **Online** — All images accessible
- **Offline** — No images accessible
- **Partial** — Some images missing
- **Never checked** — Not yet scanned

### Running a Scan

Choose a scan scope based on when galleries were last checked:

- **Scan 7+ Days** — Galleries not checked in the last 7 days
- **Scan 14+ Days**, **30+ Days**, **60+ Days**, **90+ Days**, **1+ Year**
- **Scan All** — Every completed gallery

Quick actions:

- **Rescan Offline/Partial** — Re-check only galleries currently marked as offline or partial
- **Scan Never Checked** — First-time check for unchecked galleries

### Results

After scanning, the gallery table's **online** column shows the status. You can also check individual galleries by right-clicking and selecting **Check Online Status**.

Scan statistics (total scans, galleries checked, online/offline counts) are available in **Tools > Statistics**.

!!! note
    The link scanner currently supports IMX.to galleries. Scanning runs in the background — you can close the dashboard and results will still be saved.
