# Contributing to AET

Thank you for your interest in contributing to the Airfield Ground Lighting Engineering Toolkit!

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a feature branch from `develop`
4. Make your changes
5. Submit a pull request

## Development Setup

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install development dependencies
pip install -r requirements.txt
pip install -e ".[dev]"
```

## Code Style

This project uses:

- **Black** for code formatting (line length: 88)
- **Ruff** for linting
- **Python 3.12** as the minimum supported version

Run formatting and linting before submitting:

```bash
black .
ruff check .
```

## Testing

Run the test suite with:

```bash
pytest
```

## Commit Messages

We follow [Conventional Commits](docs/standards/CONVENTIONAL_COMMITS.md). Please format your commit messages accordingly.

## Branch Strategy

- `main` — Production-ready code
- `develop` — Integration branch
- `feature/*` — Feature branches (branch from `develop`)
- `fix/*` — Bug fix branches (branch from `develop`)

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Follow the commit message conventions
4. Request review from maintainers
