# BBDrop Test Suite

## Running Tests

```bash
# All tests (parallel, 30s timeout per test)
.venv/bin/python -m pytest

# Single test file
.venv/bin/python -m pytest tests/unit/network/test_response_contract.py -v

# With coverage
.venv/bin/python -m pytest --cov=src --cov-report=html
```

## Test Structure

```
tests/
├── conftest.py                  # Shared fixtures
├── unit/
│   ├── core/                    # UploadEngine, ImageHostConfig, constants
│   ├── network/                 # FileHostClient, cookies, token cache
│   ├── gui/
│   │   ├── dialogs/             # Settings, gallery file manager
│   │   └── widgets/             # Gallery table, custom widgets
│   ├── processing/              # Upload/rename/file host workers, hooks
│   ├── proxy/                   # Proxy resolver, pool, Tor
│   └── storage/                 # Database, queue manager
├── integration/                 # Cross-module integration tests
└── performance/                 # Benchmark tests
```

## Markers

```bash
.venv/bin/python -m pytest -m unit          # Unit tests only
.venv/bin/python -m pytest -m integration   # Integration tests only
.venv/bin/python -m pytest -m smoke         # Quick smoke tests
```

## Writing Tests

- Mock all external dependencies (network, filesystem, Qt)
- Use `unittest.mock.patch` for Qt objects and pycurl
- Follow AAA pattern (Arrange, Act, Assert)
- Target >75% coverage per module
- 30-second timeout per test (enforced by pytest-timeout)

See subdirectory READMEs for module-specific test documentation.
