---
id: 20261030-editable-install
title: Editable install is required
tags: [lesson, tooling]
created: 2026-10-30
updated: 2026-10-30
related: [20261030-run-checks, 20261030-agents-md-drift]
summary: The src/ layout means tests and the CLI need `pip install -e ".[dev]"` first.
---

# Editable install is required

> Summary: The src/ layout means tests and the CLI need `pip install -e ".[dev]"` first.

## Context
[ADR-002](../../../docs/ADR/ADR-002-src-layout.md) moved the package to
`src/aet/` so that tests exercise the installed distribution instead of the
working tree. A bare checkout therefore has no importable `aet`.

## Rule
- Run `pip install -e ".[dev]"` in a fresh environment before any test, lint
  or CLI command. `ModuleNotFoundError: No module named 'aet'` means this step
  was skipped.
- Do not add `sys.path` hacks or a `conftest.py` path insert to work around it;
  that defeats the reason for the layout.

## Related
- [Running the checks](../orientation/run-checks.md) — see-also: setup step.
- [AGENTS.md drifted from the code](agents-md-drift.md) — background: AGENTS.md once said `requirements.txt`.
