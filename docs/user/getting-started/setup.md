# Setup

## From Source

```bash
git clone https://github.com/twwat/bbdrop.git
cd bbdrop
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
python bbdrop.py --gui
```

## Project Structure

```
bbdrop/
├── src/                    # Source code
│   ├── core/              # Core application logic
│   ├── gui/               # PyQt6 GUI components
│   ├── network/           # Network operations
│   ├── processing/        # Workers and tasks
│   ├── storage/           # Database and queue management
│   ├── proxy/             # Proxy pool and resolver
│   ├── services/          # Archive and notification managers
│   └── utils/             # Logging, credentials, metrics
├── tests/                 # Test suite
│   ├── unit/
│   ├── integration/
│   └── performance/
├── assets/                # Icons, styles, host definitions
├── hooks/                 # External hook scripts
├── docs/                  # Documentation
├── bbdrop.py              # Entry point
└── bbdrop.spec            # PyInstaller spec
```

## Dependencies

**Core:** Python 3.12+, PyQt6, pycurl, Pillow, cryptography, keyring

**Dev/Testing:**
```bash
pip install -r requirements-dev.txt
```

## Running Tests

```bash
# All tests (parallel, 30s timeout)
.venv/bin/python -m pytest

# Single file
.venv/bin/python -m pytest tests/unit/network/test_response_contract.py -v

# With coverage
.venv/bin/python -m pytest --cov=src --cov-report=html
```

## Configuration

- **Config file:** `~/.bbdrop/bbdrop.ini`
- **Database:** `~/.bbdrop/bbdrop.db` (SQLite, WAL mode)
- **Templates:** `~/.bbdrop/*.template.txt`
- **Credentials:** OS keyring (Fernet-encrypted)

## Building

```bash
pyinstaller bbdrop.spec
```
