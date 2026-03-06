# BBDrop

Batch-upload image galleries to multiple image and file hosts, generate BBCode, and manage persistent upload queues.

![GitHub Release](https://img.shields.io/github/v/release/twwat/bbdrop)
[![Windows](https://custom-icon-badges.demolab.com/badge/-blue.svg?logo=windows11&logoColor=white)](#)
[![macOS](https://img.shields.io/badge/-444444.svg?logo=apple&logoColor=F0F0F0)](#)
[![Linux](https://img.shields.io/badge/-yellow.svg?logo=linux&logoColor=black)](#)
[![GitHub License](https://img.shields.io/github/license/twwat/bbdrop)](https://github.com/twwat/bbdrop?tab=MIT-1-ov-file#readme)
[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/twwat/bbdrop/build.yml)](https://github.com/twwat/bbdrop/actions/workflows/build.yml)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/8ba50b3c4c82461d85c490e7ff55e641)](https://app.codacy.com/gh/twwat/bbdrop/dashboard)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/twwat/bbdrop/total)

---


## Install

### Binary _(recommended)_

[![Windows](https://custom-icon-badges.demolab.com/badge/Windows-blue.svg?logo=windows11&logoColor=white)](#)
[![macOS](https://img.shields.io/badge/macOS-444444.svg?logo=apple&logoColor=F0F0F0)](#)
[![Linux](https://img.shields.io/badge/Linux-f1c232.svg?logo=linux&logoColor=black)](#)

1. Go to the [latest release](https://github.com/twwat/bbdrop/releases/latest) page
2. Download the version for your operating system
3. Extract the archive and run the executable (e.g. `bbdrop.exe`)

_**Note**: portable versions need no installation -- unpack and run._

### From source

![Python](https://img.shields.io/badge/python-3.12+-lightgreen.svg?logo=python&logoColor=white)
[![Qt](https://img.shields.io/badge/PyQt-6.9.1-blue.svg?logo=Qt&logoColor=babyblue)](#)

```bash
git clone https://github.com/twwat/bbdrop.git
cd bbdrop
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python bbdrop.py --gui
```

---

## Usage

### GUI

```bash
python bbdrop.py --gui
```

Drag folders into the queue, configure hosts, and click Start All. Results appear in the BBCode viewer.

To send a folder to a running instance:

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

Right-click any folder and select **Add to BBDrop** to add it to the queue. Remove with `--remove-context-menu`.

---

## Supported Hosts

### Image Hosts

| Host | Auth | Max File Size | Storage | Notes |
|------|------|---------------|---------|-------|
| **IMX.to** | API / Session | Unlimited | Unlimited | Gallery/thumbnail hosting, status checking, gallery rename |
| **Pixhost** | None | 10 MB | Unlimited | Gallery hosting, pycurl-based, family/adult content types |
| **TurboImageHost** | Session | Unlimited | Unlimited | Gallery hosting, pycurl-based uploads |

### File Hosts

| Host | Auth | Max File Size | Storage | Notes |
|------|------|---------------|---------|-------|
| **FileBoom** | API | 10 GiB | 20 TiB\* | Multi-step, deduplication |
| **Filedot** | Session | Varies | 10 TiB | CAPTCHA handling, CSRF protection |
| **Filespace** | Cookie | Varies | 50+ GiB (varies) | Cookie-based auth, storage monitoring |
| **Katfile** | API | Varies | Varies | Session-based upload |
| **Keep2Share** | API | 10 GiB | 20 TiB\* | Multi-step, deduplication |
| **Rapidgator** | API / Token | 5 GiB | 4+ TiB (varies) | MD5 verification, polling |
| **TezFiles** | API | Varies | 20 TiB\* | Multi-step, deduplication |

\* 20 TiB combined storage shared between FileBoom, Keep2Share, and TezFiles.

Every host supports automatic retry, connection pooling, and token caching.

---

## Features

- 🚀 **Upload engine** — concurrent workers, drag-and-drop queue, batch processing, resume, duplicate detection, and real-time progress tracking
- 🌐 **Multi-host pipeline** — 3 image hosts and 7 file hosts through a host-agnostic architecture; queue a gallery once, upload everywhere
- 📝 **BBCode templates** — 18 placeholders, conditional blocks (`[if]...[else]...[/if]`), multiple templates, hot-swap without restarting
- 🖼️ **Cover photos** — automatic detection by filename pattern, dimensions, or file size; multi-cover support with deduplication, max-cover limiting, and per-host cover galleries
- 📦 **Archive management** — create ZIP/7Z archives with configurable compression and split sizes; extract ZIP, 7Z, RAR, TAR
- 💾 **Disk space monitoring** — tiered warnings with adaptive polling, pre-flight checks before uploads and archive creation
- 🛡️ **Proxy & Tor** — HTTP, HTTPS, SOCKS4, and SOCKS5 proxies with a 3-level resolver (global → category → per-service); built-in Tor integration with one-click pool creation and circuit rotation
- 📊 **Statistics** — upload history, bandwidth tracking, per-host metrics
- 🔍 **Link scanner** — check image availability across IMX.to galleries with configurable age thresholds
- ⚡ **Hook system** — run external scripts on upload events with positional placeholders and JSON output parsing
- 🖥️ **GUI** — PyQt6 with dark/light themes, system tray, single-instance mode, keyboard shortcuts, and audio + toast notifications

---

## BBCode Placeholders

Templates support 18 placeholders and `[if placeholder]...[else]...[/if]` conditional blocks.

<details>
<summary>All placeholders</summary>

| Placeholder | Description |
|-------------|-------------|
| `#folderName#` | Gallery or folder name |
| `#width#` | Average width |
| `#height#` | Average height |
| `#longest#` | Longest dimension |
| `#extension#` | Common format |
| `#pictureCount#` | Number of images |
| `#folderSize#` | Total size |
| `#galleryLink#` | Image host gallery URL |
| `#allImages#` | BBCode for all images except cover |
| `#cover#` | BBCode for cover image |
| `#hostLinks#` | File host download links |
| `#custom1#` -- `#custom4#` | User-defined fields |
| `#ext1#` -- `#ext4#` | External link fields (from hooks) |

</details>

---

## Configuration

All settings live in the **Settings** dialog. The default data directory is `~/.bbdrop/`; change it under Settings > General.

---

## Security

| Feature | Implementation |
|---------|---------------|
| Credential Storage | Fernet (AES-128-CBC + HMAC-SHA256) encryption with CSPRNG master key, stored in OS Keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service) |
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
<summary>System requirements</summary>

- **OS:** Windows 10+, Linux (Ubuntu 20.04+, Fedora 35+), macOS 15+
- **Python:** 3.12+ (when running from source)
- **RAM:** 512 MB minimum, 2 GB recommended
- **Disk:** 100 MB minimum, 500 MB recommended (logs/cache)

</details>

---

## Contributing

Bug reports and feature requests: [GitHub Issues](https://github.com/twwat/bbdrop/issues).

## License

MIT -- see [LICENSE](LICENSE).

---

[Docs](docs/) | [Changelog](CHANGELOG.md) | [Issues](https://github.com/twwat/bbdrop/issues)
