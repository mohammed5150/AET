# Tests

Test suite for AET.

## Running Tests

The package must be installed first — the `src/` layout means a bare
checkout has no importable copy (see
[ADR-002](../docs/ADR/ADR-002-src-layout.md)):

```bash
pip install -e ".[dev]"
pytest
```

## Structure

- Unit tests mirror the `src/aet/` package structure.
- Integration tests are in `tests/integration/`.

An autouse fixture in `conftest.py` redirects log sinks into a temporary
directory and resets process-wide logging state after each test, so a test
that configures logging cannot write into the repository or leak handlers
into later tests.
