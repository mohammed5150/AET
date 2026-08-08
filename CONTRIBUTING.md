# Contributing to AET

Thank you for your interest in contributing to the Airfield Ground Lighting Engineering Toolkit!

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a branch from `main`, named per [Branch Strategy](#branch-strategy)
4. Make your changes
5. Submit a pull request against `main`

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

`main` holds production-ready code. It is the base for every branch and the
target of every pull request; there is no separate integration branch.

Branch names carry a type prefix matching the
[Conventional Commits](docs/standards/CONVENTIONAL_COMMITS.md) type of the
work, then a short kebab-case description:

| Prefix | For |
| --- | --- |
| `feature/` | New capability |
| `fix/` | Correcting broken behaviour |
| `refactor/` | Restructuring without behaviour change |
| `docs/` | Documentation only |
| `ci/` | Build, CI, or tooling only |
| `chore/` | Maintenance with no production-code effect |

**Name the branch after the work, not after the task that started it.**
`fix/project-scoped-reads` says what the branch contains; `fix/issue-123` and
`chore/repo-status` do not, and stop being true as soon as the branch grows.

Keep one concern per branch. If a branch ends up holding separable pieces, no
single name describes it — split it and name each part, stacking the pull
requests when the pieces genuinely depend on each other (set the later PR's
base to the earlier branch).

The repository also contains a `develop` branch from an earlier flow. It is
not an integration branch and is not used; do not branch from it.

## Pull Request Process

1. Ensure `ruff check .`, `black --check .`, `mypy`, and `pytest` all pass
2. Update documentation if needed
3. Follow the commit message conventions
4. Request review from maintainers

CI runs the same four checks against Python 3.12 and 3.13 on every pull
request.
