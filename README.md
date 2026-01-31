# BBDrop

Desktop app for uploading image galleries to imx.to and 6 file hosts, generating BBCode, and tracking upload status.

![Version](https://img.shields.io/badge/version-0.8.2-blue.svg)
![Python](https://img.shields.io/badge/python-3.14+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Mac-lightgrey.svg)

![BBDrop](assets/auto.png)

---

## Install

### Binary (recommended)

1. Go to the [Releases](https://github.com/twwat/bbdrop/releases) page
2. Download the latest version for your operating system
3. Extract and run the executable (`bbdrop`)

### From source

```bash
git clone https://github.com/twwat/bbdrop.git
cd bbdrop
pip install -r requirements.txt
python bbdrop.py --gui
```

---

## Usage

### GUI

```bash
python bbdrop.py --gui
```

Drag folders into the upload queue, configure settings, and click Start All. Results appear in the BBCode viewer.

To add a folder to an already-running instance:

```bash
python bbdrop.py --gui /path/to/gallery
```

### CLI

```bash
python bbdrop.py /path/to/images
python bbdrop.py /path/to/images --name "Gallery Name" --template "Forum Post"
```

<details>
<summary>All CLI flags</summary>

| Flag | Description | Default |
|------|-------------|---------|
| `folder_paths` | Paths to folders containing images | -- |
| `-v, --version` | Print version and exit | -- |
| `--gui` | Launch GUI | off |
| `--name NAME` | Gallery name | folder name |
| `--size {1,2,3,4,6}` | Thumbnail size: 1=100, 2=180, 3=250, 4=300, 6=150 | 3 |
| `--format {1,2,3,4}` | Thumbnail format: 1=fixed width, 2=proportional, 3=square, 4=fixed height | 2 |
| `--max-retries N` | Retry attempts for failed uploads | 3 |
| `--parallel N` | Simultaneous upload count | 4 |
| `--template, -t NAME` | BBCode template name | default |
| `--setup-secure` | Set up secure password storage (interactive) | -- |
| `--rename-unnamed` | Rename all unnamed galleries from previous uploads | -- |
| `--debug` | Print all log messages to console | off |
| `--install-context-menu` | Install Windows right-click menu entry | -- |
| `--remove-context-menu` | Remove Windows right-click menu entry | -- |

</details>

### Windows context menu

```bash
python bbdrop.py --install-context-menu
```

Right-click any folder and select "Upload to imx.to (GUI)" to add it to the queue. Remove with `--remove-context-menu`.

---

## Supported Hosts

| Host | Auth | Max File Size | Storage | Notes |
|------|------|---------------|---------|-------|
| **IMX.to** | API / Session | Unlimited | Unlimited | Gallery/thumbnail hosting, status checking |
| **FileBoom** | API | 10 GiB | 20 TiB\* | Multi-step, deduplication |
| **Filedot** | Session | Varies | 10 TiB | CAPTCHA handling, CSRF protection |
| **Filespace** | Cookie | Varies | 50+ GiB (varies) | Cookie-based auth, storage monitoring |
| **Keep2Share** | API | 10 GiB | 20 TiB\* | Multi-step, deduplication |
| **Rapidgator** | API / Token | 5 GiB | 4+ TiB (varies) | MD5 verification, polling |
| **TezFiles** | API | Varies | 20 TiB\* | Multi-step, deduplication |

\* 20 TiB combined storage shared between FileBoom, Keep2Share, and TezFiles.

All hosts support automatic retry, connection pooling, and token caching.

---

## Features

- **Upload engine** -- concurrent workers, batch processing, drag-and-drop queue, resume, duplicate detection, progress tracking
- **BBCode templates** -- 18 placeholders, multiple templates, switch on the fly
- **Archive management** -- create ZIP, 7Z, RAR, TAR archives with configurable compression and split support
- **File host uploads** -- upload to any combination of 6 file hosts alongside imx.to
- **Proxy system** -- per-host SOCKS5/HTTP proxy support
- **Statistics** -- upload history, bandwidth tracking, per-host metrics
- **Online monitoring** -- check availability of previously uploaded files
- **Credential storage** -- OS keyring with encrypted fallback
- **Hook system** -- run external scripts on upload events
- **GUI** -- PyQt6, dark/light themes, system tray, single-instance mode, keyboard shortcuts, custom tabs

---

## Configuration

Config file: `~/.bbdrop/bbdrop.ini`
Data directory: `~/.bbdrop/`
Templates: `~/.bbdrop/*.template.txt`

File host credentials are configured in Settings > File Hosts. Use **Test Connection** to verify.

<details>
<summary>BBCode placeholders (18)</summary>

| Placeholder | Description |
|-------------|-------------|
| `#folderName#` | Gallery name |
| `#width#` | Average width |
| `#height#` | Average height |
| `#longest#` | Longest dimension |
| `#extension#` | Common format |
| `#pictureCount#` | Number of images |
| `#folderSize#` | Total size |
| `#galleryLink#` | imx.to gallery URL |
| `#allImages#` | BBCode for all images |
| `#hostLinks#` | File host download links |
| `#custom1#` -- `#custom4#` | User-defined fields |
| `#ext1#` -- `#ext4#` | External link fields (from hooks) |

</details>

---

## Security

| Feature | Implementation |
|---------|---------------|
| Credential Storage | OS Keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service) with Fernet AES-128-CBC fallback |
| Password Hashing | PBKDF2-HMAC-SHA256 (100,000 iterations) with cryptographic salt |
| Transport Security | TLS 1.2+ with SSL certificate verification via certifi CA bundle |
| Token Management | Encrypted token caching with configurable TTL and automatic refresh |
| Database Security | Parameterized SQL queries, SQLite WAL mode |
| Thread Safety | 60+ threading locks protecting shared state |
| Timing Attack Prevention | Constant-time password comparison via `secrets.compare_digest()` |
| Input Validation | Path normalization, SQL wildcard escaping, column whitelist validation |

---

## Building

```bash
pyinstaller bbdrop.spec
```

<details>
<summary>Development setup</summary>

```bash
git clone https://github.com/twwat/bbdrop.git
cd bbdrop
python -m venv venv
source venv/bin/activate   # Linux/Mac
./venv/scripts/activate    # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest tests/
```

</details>

<details>
<summary>Dependencies</summary>

**Core:** PyQt6 6.9.1, requests 2.32.4, pycurl 7.45.7, Pillow 11.3.0, cryptography 45.0.5, keyring 25.0+, psutil 5.9+, certifi, markdown, standard-imghdr, tqdm, colorama

**Archive:** py7zr, rarfile, splitzip

**Windows only:** pywin32-ctypes, winregistry

See `requirements.txt` for pinned versions.

</details>

<details>
<summary>System requirements</summary>

- **OS:** Windows 10+, Linux (Ubuntu 20.04+, Fedora 35+), macOS 15+
- **Python:** 3.14+ (when running from source)
- **RAM:** 512 MB minimum, 2 GB recommended
- **Disk:** 100 MB minimum, 500 MB recommended (logs/cache)

</details>

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and feature requests: [GitHub Issues](https://github.com/twwat/bbdrop/issues).

## License

MIT -- see [LICENSE](LICENSE).

---

[Docs](docs/) | [Changelog](CHANGELOG.md) | [Issues](https://github.com/twwat/bbdrop/issues)
