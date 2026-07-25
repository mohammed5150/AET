# AET — Airfield Ground Lighting Engineering Toolkit

Commercial-grade engineering toolkit for Airfield Ground Lighting (AGL) work:
design calculations, maintenance analysis, and compliance reporting for
airfield lighting systems.

## Planned scope

- **Circuits** — series-circuit and constant current regulator (CCR) sizing,
  cable and isolation-transformer calculations
- **Photometrics** — photometric test data processing and serviceability
  assessment against ICAO Annex 14 / EASA / FAA requirements
- **Maintenance** — preventive/corrective maintenance analytics and
  fitting-level history
- **Reporting** — compliance and condition reports for stakeholders

## Getting started

Requires Python 3.10+.

```bash
git clone https://github.com/mohammed5150/AET.git
cd AET
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify the installation:

```bash
python -c "import aet; print(aet.__version__)"
pytest
```

## Project layout

```
AET/
├── src/aet/          # Package source
│   ├── circuits/     # Series circuit & CCR calculations
│   ├── photometrics/ # Photometric test analysis
│   ├── maintenance/  # PM/CM analytics
│   └── reporting/    # Compliance & condition reports
├── tests/            # Test suite (pytest)
└── pyproject.toml    # Package metadata & tooling config
```

## Development

```bash
pip install -e ".[dev]"
pytest          # run tests
ruff check .    # lint
```

## Status

Early scaffold — module APIs are not yet stable.
