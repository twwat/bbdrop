# Building from source

## Prerequisites

- Python 3.12+
- Git

## Setup

```bash
git clone https://github.com/twwat/bbdrop.git
cd bbdrop
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
# GUI mode
python bbdrop.py --gui

# CLI mode
python bbdrop.py /path/to/images
```

See the [CLI reference](../user/reference/cli.md) for all available flags.

## Building an executable

```bash
pip install -r requirements-dev.txt
pyinstaller bbdrop.spec
```

## System requirements

- **OS:** Windows 10+, Linux (Ubuntu 20.04+, Fedora 35+), macOS 15+
- **Python:** 3.12+
- **RAM:** 512 MB minimum, 2 GB recommended
- **Disk:** 100 MB minimum, 500 MB recommended (logs/cache)
