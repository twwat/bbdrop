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

1. Go to the [latest release](https://github.com/twwat/bbdrop/releases/latest) page
2. Download the version for your operating system
3. Run the installer or extract the portable archive

| Platform | Recommended | Portable |
|----------|-------------|----------|
| Windows | `.exe` installer | `.zip` |
| macOS (Apple Silicon) | `.dmg` (arm64) | -- |
| macOS (Intel) | `.dmg` (x64) | -- |
| Linux | `.AppImage` | `.deb`, `.rpm` |

> Portable versions need no installation -- unpack and run.

For running from source or building executables, see [Building from source](docs/dev/building.md).

---

## Features

- **Upload engine** -- concurrent workers, drag-and-drop queue, batch processing, resume, duplicate detection, and real-time progress tracking
- **Multi-host pipeline** -- 3 image hosts and 7 file hosts through a host-agnostic architecture; queue a gallery once, upload everywhere
- **File manager** -- in-app browser for remote file hosts; browse, rename, move, copy, delete, trash, and submit remote URL uploads across all supported hosts
- **BBCode templates** -- 18+ placeholders, conditional blocks (`[if]...[else]...[/if]`), multiple templates, hot-swap without restarting
- **Cover photos** -- automatic detection by filename pattern, dimensions, or file size; multi-cover support with deduplication, max-cover limiting, and per-host cover galleries
- **Archive management** -- create ZIP/7Z archives with configurable compression and split sizes; extract ZIP, 7Z, RAR, TAR
- **Disk space monitoring** -- tiered warnings with adaptive polling, pre-flight checks before uploads and archive creation
- **Proxy & Tor** -- HTTP, HTTPS, SOCKS4, and SOCKS5 proxies with a 3-level resolver; built-in Tor integration with one-click pool creation and circuit rotation
- **Statistics** -- upload history, bandwidth tracking, per-host metrics
- **Link scanner** -- check content availability across most image and file hosts with configurable age thresholds, scan type filters, and per-host health tracking
- **Hook system** -- run external scripts on upload events with positional placeholders and JSON output parsing
- **Video support** -- metadata extraction, screenshot sheet generation, video-specific BBCode placeholders
- **GUI** -- PyQt6 with dark/light themes, system tray, single-instance mode, keyboard shortcuts, and audio + toast notifications

---

## Supported Hosts

### Image Hosts

| Host | Auth | Max File Size | Storage | Notes |
|------|------|---------------|---------|-------|
| **IMX.to** | API / Session | Unlimited | Unlimited | Affiliate program |
| **Pixhost** | None | 10 MB | Unlimited | Integrated zip download |
| **TurboImageHost** | Session | 35 MB | Unlimited | -- |

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

## Contributing

Bug reports and feature requests: [GitHub Issues](https://github.com/twwat/bbdrop/issues).

## License

MIT -- see [LICENSE](LICENSE).

---

[Docs](https://bbdrop.net) | [Changelog](CHANGELOG.md) | [Issues](https://github.com/twwat/bbdrop/issues)
