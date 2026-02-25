# Test Suite Quick Start

## Run Tests Immediately

```bash
# 1. Install dependencies (one-time setup)
.venv/bin/pip install -r requirements-dev.txt

# 2. Run all tests with coverage
.venv/bin/python -m pytest --cov=src --cov-report=html --cov-report=term

# 3. View coverage report
xdg-open htmlcov/index.html  # Linux
```

## What Gets Tested

- **125+ Unit Tests** - Configuration, memory, hooks
- **25+ Integration Tests** - Initialization, coordination
- **20+ Performance Tests** - Concurrent ops, latency benchmarks
- **>80% Coverage Target** - All metrics

## Quick Commands

```bash
# Unit tests only (fast)
.venv/bin/python -m pytest tests/unit/ -v

# Integration tests
.venv/bin/python -m pytest tests/integration/ -v

# Performance benchmarks
.venv/bin/python -m pytest tests/performance/ -v

# Parallel execution (faster)
.venv/bin/python -m pytest -n auto

# Skip slow tests
.venv/bin/python -m pytest -m "not slow"

# Single test file
.venv/bin/python -m pytest tests/unit/test_config_validation.py -v

# With detailed output
.venv/bin/python -m pytest -vv -s
```

## Coverage Requirements

All metrics must be >80%:
- Statement Coverage
- Branch Coverage
- Function Coverage
- Line Coverage

## Performance Benchmarks

- 5 concurrent agents: <60s
- Memory read: <10ms
- Memory write: <50ms
- Hook overhead: <5% of task time

## Test Files

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # 125+ unit tests
│   ├── test_config_validation.py
│   ├── test_memory_coordination.py
│   └── test_hook_execution.py
├── integration/             # 25+ integration tests
│   └── test_swarm_initialization.py
└── performance/             # 20+ performance tests
    └── test_concurrent_operations.py
```

## Documentation

- **Full Test Plan:** `docs/test-plan.md`
- **Test Suite README:** `tests/README.md`
- **Summary Report:** `docs/test-summary-report.md`

## Troubleshooting

**Import errors:**
```bash
PYTHONPATH=. .venv/bin/python -m pytest
```

**Slow tests:**
```bash
.venv/bin/python -m pytest -n auto  # Parallel execution
```

**Coverage below 80%:**
```bash
.venv/bin/python -m pytest --cov=src --cov-report=term-missing  # See missing lines
```

## Success Criteria

- All tests passing
- Coverage >80% (all metrics)
- Performance benchmarks met
- No critical bugs

---

**Ready to run!** Just execute: `.venv/bin/python -m pytest --cov=src --cov-report=html`
