# Image Hosts

Image hosts are where your gallery images are uploaded and viewed. BBDrop supports two image hosts, each with different features and requirements.

## Enabling a Host

There are several ways to access host configuration:

- **Right-click** a host in the Upload Workers table and select **Enable Host** or **Configure Host**
- **Double-click** a host in the Upload Workers table
- Click the **Image Hosts** button in the quick settings panel
- Go to **Settings > Image Hosts**

## TurboImageHost

TurboImageHost works without credentials — enable it and start uploading immediately.

**Optional credentials:** Creating a free account lets you manage your uploads on the TurboImageHost website. Enter your username and password in the host configuration dialog.

### Settings

- **Thumbnail size** — Variable slider from 150px to 600px (default: 350px)
- **Thumbnail format** — Proportional or square crop
- **Content type** — Family Safe or Adult content filtering
- **Max gallery images** — 500 images per gallery (host limit)
- **Max file size** — 35 MB per image (host limit)

## IMX.to

IMX.to requires authentication. You can use either an API key or session-based login.

### Authentication

Open the IMX.to host configuration and enter your credentials:

- **API Key** — Get this from your IMX.to account settings. Paste it into the API Key field.
- **Session login** — Enter your username and password. BBDrop will authenticate and maintain the session.

All credentials are encrypted before being stored in your operating system's keyring (Windows Credential Manager, macOS Keychain, or Linux Secret Service).

!!! note
    You can test your credentials at any time using the **Test Connection** button in the host configuration dialog.

### Settings

- **Thumbnail size** — Preset sizes: 100x100, 150x150, 180x180, 250x250 (default), 300x300
- **Thumbnail format** — JPEG 70%, JPEG 90% (default), PNG, WebP
- **Gallery visibility** — Public or private galleries

### Unnamed Galleries

IMX.to creates galleries without names by default. BBDrop includes a **RenameWorker** that automatically renames galleries using the folder name after upload completes. This runs in the background and requires an active session.

You can view and manage unnamed galleries from **Tools > Unnamed Galleries**.

!!! important
    Gallery renaming requires an active IMX.to session. If you're using API key authentication only, the RenameWorker will authenticate separately using your stored credentials.

## Per-Gallery Host Assignment

Each gallery in the queue has an **image host** column. You can change which host a gallery uploads to by:

- Clicking the image host cell and selecting from the dropdown
- Right-clicking and using **Set image host to...** for bulk changes

The **Image Host** dropdown in Quick Settings sets the default for newly added galleries.

## Connection Settings

Each host has configurable connection settings in its configuration dialog:

- **Auto-retry** — Automatically retry failed uploads
- **Max retries** — Number of retry attempts (default: 2)
- **Max connections** — Concurrent upload threads (default varies by host)
- **Inactivity timeout** — Seconds before a stalled upload is considered failed
- **Max upload time** — Maximum time allowed per upload

## Host Metrics

Each host tracks upload statistics visible in the configuration dialog:

| Metric | Tracked Per |
|--------|-------------|
| Uploaded (bytes) | Session, Today, All Time |
| Files uploaded | Session, Today, All Time |
| Average speed | Session, Today, All Time |
| Peak speed | Session, Today, All Time |
| Success rate | Session, Today, All Time |

These metrics are also available as optional columns in the Upload Workers table — right-click the column header to add them.
