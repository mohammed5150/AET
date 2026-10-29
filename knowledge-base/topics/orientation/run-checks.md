---
id: 20261030-run-checks
title: Running the checks
tags: [orientation, tooling]
created: 2026-10-30
updated: 2026-10-30
related: [20261030-editable-install, 20261030-session-protocol]
summary: The one command that reproduces CI locally, and the baseline it should report.
---

# Running the checks

> Summary: The one command that reproduces CI locally, and the baseline it should report.

## Context
CI (`.github/workflows/ci.yml`) runs ruff, black, mypy, pytest with coverage
and `aet version` on Python 3.12 and 3.13. `scripts/check.sh` runs the same
steps in the same order, so a local pass predicts a CI pass on that Python.

## Details

### Setup (once per checkout)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Run
```bash
scripts/check.sh
```

### Baseline
On 30-Oct-2026 (commit `fb0c367`, Python 3.13): all linters clean,
pytest 429 passed and 1 skipped (416 before the knowledge-base tests were
added), `aet version` → `aet 0.1.0`. With coverage on, 39
`ResourceWarning: unclosed database` warnings are a known open item (see
WORKLOG). A drop in the
passed count without a matching test removal means tests stopped being
collected; investigate before continuing.

## Related
- [Editable install is required](../lessons/editable-install.md) — prerequisite: the checks fail to import without it.
- [Session protocol](session-protocol.md) — see-also: when in a session to run them.
