# AGENTS.md — Guidance for AI Coding Agents

This file provides context and rules for AI agents (e.g., GitHub Copilot,
Codex, Claude) working in this repository.

---

## Project Overview

**AET** is a commercial-grade **Airfield Ground Lighting (AGL) Engineering
Toolkit** written in Python 3.12. It ingests DWG/CAD drawing files, interprets
drawing entities, derives engineering assets, validates them against domain
rules, and produces auditable engineering reports.

The architecture is a **layered modular monolith** with a plugin-ready
boundary. See [SDS-002](docs/SDS/SDS-002-System-Architecture.md) for the full
architecture specification and [ADR-001](docs/ADR/ADR-001-sds-002-package-mapping.md)
for the mapping between SDS-002 module names and the actual package layout.

---

## Repository Layout

```
app/                  # Application source (the only installed package)
├── core/             # Cross-cutting infrastructure
│   ├── config.py     # AppConfig and PLUGIN_API_VERSION constant
│   ├── errors.py     # AETError hierarchy (InputError, ProcessingError, …)
│   ├── logging.py    # StructuredLogger + get_logger()
│   ├── outcome.py    # Outcome[T] — the universal processing result type
│   └── plugins.py    # Plugin / PluginRuntime contracts
├── models/           # Domain entities and value objects
├── modules/          # Feature engines
│   ├── ingestion/    # DWG/file ingestion
│   ├── drawing_engine/
│   ├── asset_engine/
│   ├── validation_engine/
│   └── reporting_engine/
├── services/         # Use-case orchestration and persistence
│   ├── use_cases.py
│   ├── pipeline.py
│   └── persistence.py
└── ui/               # CLI entry-point (app.ui.cli:main → `aet` command)

docs/
├── SDS/              # Software Design Specifications
├── ADR/              # Architecture Decision Records
├── standards/        # Coding and commit-message standards
└── roadmap/

tests/                # pytest suite — mirrors app/ structure
├── core/
├── models/
├── modules/
├── services/
├── ui/
└── integration/

config/               # Runtime configuration files
scripts/              # Build and utility scripts
examples/             # End-to-end usage demos
output/               # Generated outputs (git-ignored)
logs/                 # Log files (git-ignored)
```

**Dependency direction (enforced by convention, not tooling):**
`ui → services → models`; engines depend only on `models` and `core`;
plugins depend only on `app.core.plugins` contracts.

---

## Development Environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

Minimum Python version: **3.12** (uses PEP 695 generics, `StrEnum`, `slots=True`).

---

## Key Commands

| Purpose | Command |
|---|---|
| Run all tests | `pytest` |
| Run tests with coverage | `pytest --cov=app` |
| Format code | `black .` |
| Lint | `ruff check .` |
| Lint + auto-fix | `ruff check --fix .` |
| Run the CLI | `aet run --name "Demo" path/to/drawing.dwg` |

Always run `black .` and `ruff check .` before committing code changes.

---

## Code Conventions

### Formatting & Linting

- **Black** — line length 88, target Python 3.12.
- **Ruff** — rules: `E`, `W`, `F` (pyflakes), `I` (isort), `N` (pep8-naming),
  `UP` (pyupgrade). Fix all Ruff warnings before committing.
- Use `from __future__ import annotations` in every module.
- Prefer `dataclasses.dataclass(frozen=True, slots=True)` for value objects.

### Error Handling

- **Never raise raw exceptions across module boundaries.** Wrap expected
  failures in an `Outcome.fail(...)` return value instead.
- For unexpected system errors, let ordinary exceptions propagate so they are
  distinguishable from domain errors.
- Use the `AETError` subclass hierarchy in `app.core.errors`:
  - `InputError` — bad inputs / unsupported formats
  - `ProcessingError` — parsing / transformation failures
  - `RuleError` — validation rule failures
  - `InfrastructureError` — DB / plugin / config failures
  - `WorkflowError` — invalid operation sequencing

### Outcome Contract

Every processing step **must return `Outcome[T]`**, never raise across the
module boundary:

```python
from app.core.outcome import Outcome

def process(...) -> Outcome[MyResult]:
    try:
        result = ...
        return Outcome.ok(result, correlation_id=cid)
    except AETError as exc:
        return Outcome.from_error(exc, correlation_id=cid)
```

### Logging

Use `get_logger(name)` from `app.core.logging` — never `print()` or
`logging.getLogger()` directly:

```python
from app.core.logging import get_logger
logger = get_logger("my-module")
logger.info("message", key=value)       # structured fields
logger.audit("...", operation="...")    # audit-trail events
```

### Plugins

New plugins must subclass `app.core.plugins.Plugin`, provide a valid
`PluginManifest`, and be registered through `PluginRuntime.register()`.
Plugins may **not** import anything outside `app.core.plugins`, `app.core.config`,
and `app.core.logging`.

---

## Testing

- Tests live under `tests/` and mirror the `app/` package structure.
- Integration tests go in `tests/integration/`.
- Test files are named `test_*.py`; test functions are named `test_*`.
- Do not delete or weaken existing tests. Add new tests for every behaviour
  change and for bug fixes.
- Aim for unit tests that test a single function/class in isolation;
  use fixtures for shared setup.

---

## Commit Messages

Follow [Conventional Commits](docs/standards/CONVENTIONAL_COMMITS.md).

Format: `<type>(<scope>): <subject>`

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`

**Scopes:** `drawing-engine`, `asset-engine`, `validation-engine`,
`reporting-engine`, `ingestion`, `core`, `ui`, `services`, `repository-foundation`

Rules:
- Subject in imperative present tense, lowercase, no trailing period, ≤ 50 chars.
- Body is optional but recommended for non-trivial changes.
- Reference issues in the footer: `Fixes #123`, `Closes #456`.

Example:
```
feat(drawing-engine): implement DWG parser for line entities

Add support for parsing LINE entities from DWG files.
Includes coordinate extraction and layer mapping.

Fixes #42
```

---

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready code |
| `develop` | Integration branch — PRs target here |
| `feature/*` | New features (branch from `develop`) |
| `fix/*` | Bug fixes (branch from `develop`) |

---

## Pull Request Checklist

Before opening a PR ensure:

1. `black .` passes with no changes.
2. `ruff check .` reports no errors.
3. `pytest` passes with no failures.
4. New behaviour is covered by tests.
5. Commit messages follow Conventional Commits.
6. Documentation updated if public interfaces changed.

---

## Architecture Constraints for Agents

When generating or modifying code, respect these invariants:

1. **Layer boundaries** — `ui` may import `services`; `services` may import
   `models` and `core`; engines (`modules/*`) may only import `models` and
   `core`. Do not create circular imports across layers.
2. **Outcome everywhere** — module-to-module calls return `Outcome[T]`.
   Do not raise `AETError` across a module boundary; wrap it with
   `Outcome.from_error(exc)`.
3. **No silent failures** — every processing step that can fail must log the
   failure and return a failed `Outcome` with a machine-readable `error_code`.
4. **Plugin isolation** — plugins are activated through `PluginRuntime` only.
   Activation failures must be quarantined, not re-raised.
5. **Structured logging** — always use `get_logger` from `app.core.logging`.
   Never use `print()` in production code paths.
6. **Python 3.12 features are encouraged** — use `X | Y` union syntax,
   `type` aliases, `slots=True`, `StrEnum`, etc.
