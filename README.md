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
