# AGENTS.md — Guidance for AI Coding Agents

This file provides context and rules for AI agents (e.g., GitHub Copilot,
Codex, Claude) working in this repository.

Before starting work, read [knowledge-base/INDEX.md](knowledge-base/INDEX.md)
and the latest entries in
[knowledge-base/WORKLOG.md](knowledge-base/WORKLOG.md). Before finishing,
follow the session routine in
[knowledge-base/topics/orientation/session-protocol.md](knowledge-base/topics/orientation/session-protocol.md).

---

## Project Overview

**AET** is a commercial-grade **Airfield Ground Lighting (AGL) Engineering
Toolkit** written in Python 3.12. It ingests DWG/CAD drawing files, interprets
drawing entities, derives engineering assets, validates them against domain
rules, and produces auditable engineering reports.

The architecture is a **layered modular monolith** with a plugin-ready
boundary. See [SDS-002](docs/SDS/SDS-002-System-Architecture.md) for the full
architecture specification, [ADR-001](docs/ADR/ADR-001-sds-002-package-mapping.md)
for the mapping between SDS-002 module names and the package layout, and
[ADR-002](docs/ADR/ADR-002-src-layout.md) for the `src/` layout.

---

## Repository Layout

```
src/aet/              # Application source (the only installed package)
├── core/             # Cross-cutting infrastructure
│   ├── config.py     # AppConfig and PLUGIN_API_VERSION constant
│   ├── discovery.py  # Plugin discovery from disk and entry points (SDS-014)
│   ├── errors.py     # AETError hierarchy (InputError, ProcessingError, …)
│   ├── logging.py    # StructuredLogger + get_logger()
│   ├── outcome.py    # Outcome[T] — the universal processing result type
│   └── plugins.py    # Plugin / PluginRuntime contracts
├── models/           # Domain entities and value objects
├── modules/          # Feature engines
│   ├── ingestion/
│   ├── drawing_engine/
│   ├── asset_engine/
│   ├── validation_engine/
│   └── reporting_engine/
├── services/         # Use-case orchestration and persistence
│   ├── use_cases.py
│   ├── pipeline.py
│   ├── persistence.py
│   ├── sqlite.py
│   ├── serialization.py
│   └── reference_library.py
├── ui/               # CLI entry-point (aet.ui.cli:main → `aet` command)
├── utils/            # Hashing and identifier helpers
└── resources/        # Static resources and data files

docs/
├── SDS/              # Software Design Specifications
├── ADR/              # Architecture Decision Records
├── Standards/        # Coding and engineering standards
├── standards/        # Commit-message standard
├── Reference/        # How AET refers to authoritative references
└── roadmap/

knowledge-base/       # Agent knowledge base: repo map, lessons, worklog

tests/                # pytest suite — mirrors src/aet/ structure
├── core/
├── models/
├── modules/
├── services/
├── ui/
└── integration/

config/               # Runtime configuration files
scripts/              # Build and utility scripts (check.sh runs the CI gate)
examples/             # End-to-end usage demos
output/               # Generated outputs (git-ignored)
logs/                 # Log files (git-ignored)
```

**Dependency direction (enforced by convention, not tooling):**
`ui → services → models`; engines depend only on `models` and `core`;
plugins depend only on `aet.core.plugins` contracts.

---

## Development Environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

`pyproject.toml` is the single source of truth for dependencies; there is no
requirements file. The editable install is required: the `src/` layout means a
bare checkout has no importable copy of the package (ADR-002).

Minimum Python version: **3.12** (uses PEP 695 generics, `StrEnum`, `slots=True`).

---

## Key Commands

| Purpose | Command |
|---|---|
| Run the full CI gate locally | `scripts/check.sh` |
| Run all tests | `pytest` |
| Run tests with coverage | `pytest --cov=aet` |
| Format code | `black .` |
| Lint | `ruff check .` |
| Lint + auto-fix | `ruff check --fix .` |
| Type-check | `mypy` |
| Run the CLI | `aet run --name "Demo" path/to/drawing.dxf` |

Run `scripts/check.sh` before committing. It runs the same steps as CI.

---

## Code Conventions

### Formatting & Linting

- **Black** — line length 88, target Python 3.12.
- **Ruff** — the rule set in `pyproject.toml` (`E`, `W`, `F`, `I`, `N`, `UP`,
  `B`, `BLE`, `S`, `C4`, `SIM`, `PTH`, `PT`, `RET`, `RUF`). Fix all Ruff
  warnings before committing.
- **mypy** — `strict` over `src` and `tests`.
- Use `from __future__ import annotations` in every module.
- Prefer `dataclasses.dataclass(frozen=True, slots=True)` for value objects.

### Error Handling

- **Never raise raw exceptions across module boundaries.** Wrap expected
  failures in an `Outcome.fail(...)` return value instead.
- For unexpected system errors, let ordinary exceptions propagate so they are
  distinguishable from domain errors.
- Use the `AETError` subclass hierarchy in `aet.core.errors`:
  - `InputError` — bad inputs / unsupported formats
  - `ProcessingError` — parsing / transformation failures
  - `RuleError` — validation rule failures
  - `InfrastructureError` — DB / plugin / config failures
  - `WorkflowError` — invalid operation sequencing

### Outcome Contract

Every processing step **must return `Outcome[T]`**, never raise across the
module boundary:

```python
from aet.core.outcome import Outcome

def process(...) -> Outcome[MyResult]:
    try:
        result = ...
        return Outcome.ok(result, correlation_id=cid)
    except AETError as exc:
        return Outcome.from_error(exc, correlation_id=cid)
```

### Logging

Use `get_logger(name)` from `aet.core.logging` — never `print()` or
`logging.getLogger()` directly:

```python
from aet.core.logging import get_logger
logger = get_logger("my-module")
logger.info("message", key=value)       # structured fields
logger.audit("...", operation="...")    # audit-trail events
```

### Plugins

New plugins must subclass `aet.core.plugins.Plugin`, provide a valid
`PluginManifest`, and be registered through `PluginRuntime.register()`.
Plugins may **not** import anything outside `aet.core.plugins`, `aet.core.config`,
and `aet.core.logging`.

### Engineering limits

No regulatory or engineering limit is shipped as a default
([SDS-012](docs/SDS/SDS-012-AGL-Engineering-Rules.md) §4). Never hardcode a
spacing, loading or photometric value from memory. Criteria belong to the
controlled module that SDS-016 §16 defers, and AET records where a reference
document is without holding it ([ADR-003](docs/ADR/ADR-003-controlled-reference-documents.md)).

---

## Testing

- Tests live under `tests/` and mirror the `src/aet/` package structure.
- Integration tests go in `tests/integration/`.
- Test files are named `test_*.py`; test functions are named `test_*`.
- Do not delete or weaken existing tests. Add new tests for every behaviour
  change and for bug fixes.
- Aim for unit tests that test a single function/class in isolation;
  use fixtures for shared setup.
- `tests/test_knowledge_base.py` checks the knowledge base structure. Keep it
  passing when you add or rename notes.

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

`main` holds production-ready code. It is the base for every branch and the
target of every pull request; there is no integration branch. Branch names
carry a type prefix (`feature/`, `fix/`, `refactor/`, `docs/`, `ci/`,
`chore/`) and a kebab-case description of the work. Full rules:
[CONTRIBUTING](CONTRIBUTING.md#branch-strategy).

---

## Pull Request Checklist

Before opening a PR ensure:

1. `scripts/check.sh` passes (ruff, black, mypy, pytest, CLI entry point).
2. New behaviour is covered by tests.
3. Commit messages follow Conventional Commits.
4. Documentation updated if public interfaces changed.
5. `knowledge-base/WORKLOG.md` has an entry for the session, and any new
   lesson is recorded as a note.

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
5. **Structured logging** — always use `get_logger` from `aet.core.logging`.
   Never use `print()` in production code paths.
6. **Python 3.12 features are encouraged** — use `X | Y` union syntax,
   `type` aliases, `slots=True`, `StrEnum`, etc.
