# AET

Commercial-grade Airfield Ground Lighting (AGL) Engineering Toolkit

## Project Structure

```
src/aet/              # Application source code (importable package)
├── core/             # Core functionality and base classes
├── ui/               # User interface components
├── modules/          # Feature modules
├── services/         # Service layer
├── models/           # Data models and schemas
├── utils/            # Utility functions and helpers
└── resources/        # Static resources and data files

docs/                 # Documentation
├── SDS/              # Software Design Specifications
├── ADR/              # Architecture Decision Records
├── Standards/        # Coding and engineering standards
└── Images/           # Documentation images and diagrams

tests/                # Test suite
examples/             # Example scripts and usage demos
scripts/              # Build and utility scripts
config/               # Configuration files
assets/               # Static assets
output/               # Generated output (git-ignored)
logs/                 # Log files (git-ignored)
```

## Architecture

The system architecture is defined in
[SDS-002](docs/SDS/SDS-002-System-Architecture.md): a layered modular
monolith with a pipeline-oriented processing core (ingestion → drawing
interpretation → asset derivation → validation → reporting), structured
outcomes and error boundaries, structured/audit logging, repository-based
persistence, and a plugin runtime for importers, interpreters, extractors,
validation rules, and report providers.

How SDS-002 modules map onto this repository's layout is recorded in
[ADR-001](docs/ADR/ADR-001-sds-002-package-mapping.md).

Run the whole pipeline in one shot:

```bash
aet run --name "Demo Project" path/to/drawing.dxf
```

Or work a project across separate commands, keeping state in a database:

```bash
export AET_DATABASE=./aet.db
aet project create "Taxiway Kilo"
aet import "Taxiway Kilo" taxiway.dxf --registry assets.xlsx
aet process "Taxiway Kilo"
aet validate "Taxiway Kilo"     # exits 2 if a rule fails
aet report "Taxiway Kilo"
```

## Configuration

Settings resolve in layers, each overriding the one before it: built-in
defaults, then environment variables, then CLI flags.

| Setting | Environment variable | CLI flag | Default |
| --- | --- | --- | --- |
| Generated artifacts | `AET_DATA_DIR` | `--data-dir` | `output/` |
| Log destination | `AET_LOG_DIR` | `--log-dir` | `logs/` |
| Log verbosity | `AET_LOG_LEVEL` | `--log-level` | `INFO` |
| Plugin search path | `AET_PLUGIN_DIRS` | — | none |

`AET_PLUGIN_DIRS` holds an `os.pathsep`-separated list of directories.

The CLI writes two structured JSON log streams into the log directory, kept
separate per [SDS-002](docs/SDS/SDS-002-System-Architecture.md) §11.5:

- `aet.log` — diagnostic records, also echoed to stderr
- `audit.log` — the immutable audit trail of significant processing actions

Library callers get no log sinks until they call `configure_logging`
themselves; without it the standard library discards everything below
WARNING.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`pyproject.toml` is the single source of truth for dependencies; there is no
separate requirements file. The editable install is required, not optional —
the `src/` layout means a bare checkout has no importable copy of the package
(see [ADR-002](docs/ADR/ADR-002-src-layout.md)).

## Tools

- **Python 3.12** — the supported floor, pinned for local work in
  `.python-version`; 3.13 is also tested
- **Black** — code formatting
- **Ruff** — linting
- **mypy** — type checking, in `strict` mode
- **pytest** — testing

Every push to `main` and every pull request runs all four against Python 3.12
and 3.13 via [GitHub Actions](.github/workflows/ci.yml). Run the same checks
locally before pushing:

```bash
ruff check . && black --check . && mypy && pytest
```

## License

MIT — see [LICENSE](LICENSE) for details.
