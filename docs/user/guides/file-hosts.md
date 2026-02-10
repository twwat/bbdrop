# File Hosts

File hosts let you distribute compressed archives of your galleries for download. When enabled, BBDrop automatically creates a ZIP or 7Z archive and uploads it to each active file host.

## Available Hosts

Seven file hosts are available: **RapidGator**, **FileBoom**, **Keep2Share**, **TezFiles**, **Filedot**, **Filespace**, and **KatFile**. All require credentials (username and password).

## Setting Up a File Host

Open the configuration dialog for any file host by:

- Right-clicking it in the Upload Workers table and selecting **Configure Host**
- Double-clicking it in the Upload Workers table
- Clicking **File Hosts** in the quick settings panel
- Going to **Settings > File Hosts**

### Credentials

Enter your username and password for the host. Credentials are encrypted and stored in your operating system's keyring. Click **Test Connection** to verify — it runs four checks:

1. **Credentials** — Can authenticate with the host
2. **User info** — Can retrieve account information
3. **Upload test** — Can upload a small test file
4. **Delete test** — Can delete the test file

### Storage Monitoring

The configuration dialog shows a storage bar with used and available space. This updates automatically when the host is active.

## Auto-Upload Triggers

Each file host has an **Auto-Upload Trigger** setting that controls when archive uploads start:

- **On Started** — Upload archive as soon as the gallery starts uploading images
- **On Completed** — Upload archive only after all images are uploaded successfully
- **Manual** — Only upload when manually triggered

## Archive Settings

Configure archive format and compression in **Settings > Archive**:

### Format

- **ZIP** — Universal compatibility. Compression options: Store (no compression), Deflate (default), LZMA, BZip2
- **7-Zip** — Better compression ratios. Compression options: Copy (no compression), LZMA2 (default), LZMA, Deflate, BZip2

### Split Archives

For large galleries, enable split archives to break them into multiple parts:

- **Enable split archives** — Toggle on/off
- **Split size** — 100 MiB to 4,095 MiB per part

Split archives are named `gallery_name.zip.001`, `gallery_name.zip.002`, etc.

!!! note
    ZIP splitting uses a built-in pure Python implementation and works everywhere. 7Z splitting requires the 7-Zip CLI to be installed on your system.

## Per-Host Settings

Each file host has its own connection settings:

- **Max retries** — Retry attempts on failure
- **Max connections** — Concurrent uploads to this host
- **Max file size** — Largest file the host accepts
- **Inactivity timeout** — Seconds before a stalled upload is considered failed
- **Max upload time** — Maximum time allowed per upload
- **BBCode format** — Template for how download links appear in your BBCode output (uses `#link#`, `#hostName#`, `#partLabel#`, `#partNumber#`, `#partCount#` placeholders)
- **Proxy** — Per-host proxy selection

## Host Metrics

Each file host tracks the same set of metrics as image hosts (uploaded bytes, file count, speed, success rate) across Session, Today, and All Time periods. View them in the host configuration dialog or as columns in the Upload Workers table.
