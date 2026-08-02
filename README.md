# AET

Commercial-grade Airfield Ground Lighting (AGL) Engineering Toolkit

## Project Structure

```
app/                  # Application source code
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

Try the walking skeleton end to end:

```bash
aet run --name "Demo Project" path/to/drawing.dwg
```

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

## Tools

- **Python 3.12**
- **Black** — Code formatting
- **Ruff** — Linting
- **pytest** — Testing

## License

MIT — see [LICENSE](LICENSE) for details.
