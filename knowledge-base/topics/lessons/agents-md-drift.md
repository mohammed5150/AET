---
id: 20261030-agents-md-drift
title: AGENTS.md drifted from the code
tags: [lesson, docs, process]
created: 2026-10-30
updated: 2026-10-30
related: [20261030-repo-map, 20261030-editable-install]
summary: AGENTS.md described an app/ package and a develop branch that no longer exist; which files govern instead.
---

# AGENTS.md drifted from the code

> Summary: AGENTS.md described an app/ package and a develop branch that no longer exist; which files govern instead.

## What happened
On 30-Oct-2026 AGENTS.md still described the pre-ADR-002 repository: an
`app/` package, `pip install -r requirements.txt`, PRs targeting `develop`,
and imports from `app.core.*`. The code had moved to `src/aet/`, the
requirements file had been removed, and CONTRIBUTING says `develop` is unused.
An agent following AGENTS.md would have used wrong paths and the wrong base
branch.

## Evidence
- [ADR-002](../../../docs/ADR/ADR-002-src-layout.md) supersedes the `app/` layout.
- [CONTRIBUTING](../../../CONTRIBUTING.md) Branch Strategy: every PR targets `main`.
- `pyproject.toml` lists dependencies; no `requirements.txt` exists.

## Rule
- Where AGENTS.md and an ADR, CONTRIBUTING or `pyproject.toml` disagree, the
  ADR / CONTRIBUTING / `pyproject.toml` govern. Fix AGENTS.md in the same change.
- Any PR that moves a package, changes a command or changes the branch flow
  must update AGENTS.md and the [repository map](../orientation/repo-map.md).

## Related
- [Repository map](../orientation/repo-map.md) — see-also: the layout as it stands.
- [Editable install is required](editable-install.md) — supports: the same ADR change.
