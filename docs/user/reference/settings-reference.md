# Settings Reference

All settings are accessible from **Settings** in the quick settings panel or the **Settings** menu. The dialog has the following tabs.

## General

**General Options:**

| Setting | Description | Default |
|---|---|---|
| Confirm when removing galleries | Show confirmation before removing galleries | On |
| Auto-regenerate artifacts when data changes | Regenerate BBCode when template, name, or fields change | On |
| Start uploads automatically | Start uploads as soon as scanning completes | Off |
| Clear completed items automatically | Remove completed galleries from queue | Off |
| Check for updates on startup | Check GitHub for new releases at launch | On |

**Central Storage** — Where BBDrop stores its database, artifacts, and settings:

- **Home folder** — `~/.bbdrop` (default)
- **App folder (portable)** — Next to the application executable
- **Custom location** — User-specified directory

**Gallery Artifacts** — Where BBCode and JSON files are saved:

- **Save in '.uploaded' subfolder** — Inside the gallery folder (default: on)
- **Save in central storage** — In the central storage directory (default: on)

**Appearance:**

| Setting | Description | Default |
|---|---|---|
| Theme mode | Light or Dark | Dark |
| Text size | Base font size (6-24pt) | 9pt |
| Show icons only on quick settings buttons | Hide button text labels | Off |
| Show file host logos in upload workers table | Display logos instead of text names | On |

## Image Hosts

Lists all available image hosts. Click **Configure** on any host to open its settings dialog with credentials, thumbnail options, connection settings, and metrics.

## File Hosts

Lists all available file hosts. Click **Configure** on any host to open its settings dialog with credentials, storage monitoring, auto-upload triggers, connection settings, BBCode format, proxy, and metrics.

## Templates

Embedded template manager for creating, editing, copying, and deleting BBCode templates. See [BBCode Templates](../guides/templates.md) for full details.

## Image Scan

**Scanning Strategy:**

| Setting | Description | Default |
|---|---|---|
| Use fast corruption checking | Quick corruption detection via imghdr with PIL fallback | On |

**Dimension Sampling:**

| Setting | Description | Default |
|---|---|---|
| Method | Fixed count or Percentage of images | Fixed count |
| Fixed count | Number of images to sample | 25 |
| Percentage | Percent of images to sample | 10% |

**Exclusions:**

| Setting | Description | Default |
|---|---|---|
| Skip first image | Often a cover/poster | Off |
| Skip last image | Often credits/logo | Off |
| Skip images smaller than X% | Filter out thumbnails and previews | 50% |
| Skip filename patterns | Comma-separated wildcards (e.g., `cover*, thumb*`) | Empty |

**Statistics:**

| Setting | Description | Default |
|---|---|---|
| Exclude outliers (1.5 IQR) | Remove dimension outliers | Off |
| Average method | Mean or Median | Median |

## Hooks

Configure external program hooks for three gallery lifecycle events. See [Hooks & Automation](../guides/hooks.md) for full details.

## Proxy

Configure global proxy mode and proxy pools. See [Proxies](../guides/proxies.md) for full details.

## Logs

**GUI Log:**

| Setting | Description | Default |
|---|---|---|
| Log level | Minimum severity shown in GUI log panel | INFO |
| Upload success detail | Detail level for success messages | Gallery |
| Show log level prefix | Show DEBUG:, ERROR:, etc. prefixes | Off |
| Show category tags | Show [network], [uploads], etc. tags | Off |
| Categories | Toggle individual log categories (Uploads, Authentication, Network, UI, Queue, Renaming, File I/O, Database, Timing, General) | All on |

**File Logging:**

| Setting | Description | Default |
|---|---|---|
| Enable file logging | Write logs to disk | On |
| Rotation | Daily, weekly, or by size | Daily |
| Backups to keep | Number of rotated log files to retain | 365 |
| Compress rotated logs | Gzip old log files | On |
| Max size | Maximum log file size (size rotation mode) | 10 MB |
| Log level | Minimum severity written to file | DEBUG |
| Upload success detail | Detail level for success messages | Gallery |

## Archive

Configure archive format, compression, and splitting for file host uploads. See [File Hosts](../guides/file-hosts.md#archive-settings) for full details.

## Advanced

Power-user settings displayed in a searchable table. These are rarely needed but available for fine-tuning:

| Setting | Description | Default |
|---|---|---|
| `gui/log_font_size` | Font size for GUI log display | 10 |
| `uploads/retry_delay_seconds` | Seconds before retrying a failed upload | 5 |
| `scanning/skip_hidden_files` | Skip files starting with `.` | True |
| `bandwidth/alpha_up` | Speed display attack rate (how fast it rises) | 0.6 |
| `bandwidth/alpha_down` | Speed display release rate (how fast it decays) | 0.35 |
