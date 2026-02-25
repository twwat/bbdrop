# Testing Setup Guide

## Installation Steps

### 1. Install Testing Dependencies

From the project root:

```bash
# Install test dependencies
.venv/bin/pip install -r requirements-dev.txt
```

### 2. Verify Installation

```bash
# Check pytest is installed
.venv/bin/python -m pytest --version

# Check pytest-cov is installed
.venv/bin/python -m pytest --help | grep cov
```

### 3. Run Tests

```bash
# Run all tests with coverage
.venv/bin/python -m pytest --cov=src --cov-report=html

# Run specific test categories
.venv/bin/python -m pytest tests/unit/              # Unit tests only
.venv/bin/python -m pytest tests/integration/       # Integration tests only
.venv/bin/python -m pytest tests/performance/       # Performance tests only

# Run with verbose output
.venv/bin/python -m pytest -v --cov=src

# Run in parallel (faster)
.venv/bin/python -m pytest -n auto --cov=src
```

### 4. View Coverage Report

After running tests with `--cov-report=html`:

```bash
# Open the coverage report in browser
xdg-open htmlcov/index.html

# Or on Windows WSL
explorer.exe htmlcov/index.html

# Or just view the text summary
.venv/bin/python -m pytest --cov=src --cov-report=term
```

## Common Issues

### Issue: "pytest: error: unrecognized arguments: --cov"

**Solution**: Install pytest-cov:
```bash
.venv/bin/pip install pytest-cov
```

### Issue: "No module named 'src'"

**Solution**: Run tests from project root:
```bash
.venv/bin/python -m pytest --cov=src --cov-report=html
```

### Issue: "Permission denied"

**Solution**: Use the project venv:
```bash
.venv/bin/pip install -r requirements-dev.txt
```

## Quick Start

```bash
# One-liner to install and run tests
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest --cov=src --cov-report=html
```

## Alternative: Run Without Coverage

If you just want to run tests without coverage:

```bash
.venv/bin/python -m pytest tests/
```
