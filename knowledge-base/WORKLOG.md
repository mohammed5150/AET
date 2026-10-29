# Worklog

One entry per working session, newest first. Keep each entry short:
what changed, how it was verified, and what is left open.

Entry format:

```
## YYYY-MM-DD — <short title>
- Changed: …
- Verified: <command> → <result>
- Open: … (or "none")
- Lessons: <note ids added or updated> (or "none")
```

## 2026-10-30 — Agent knowledge base set up
- Changed: corrected AGENTS.md (src/aet layout, no requirements file, no
  develop branch, mypy in the gate); added CLAUDE.md, `scripts/check.sh`,
  this knowledge base and `tests/test_knowledge_base.py`.
- Verified: baseline before changes `scripts/check.sh` equivalent → ruff,
  black, mypy clean; pytest 416 passed, 1 skipped; `aet version` → aet 0.1.0.
  After changes: `scripts/check.sh` → all steps pass, pytest 429 passed,
  1 skipped (13 new knowledge-base tests).
- Open: under `--cov`, pytest reports 39 `ResourceWarning: unclosed database`
  (sqlite3 connections not closed); present before this change, cause not yet
  traced. The remote still has a stale `develop` branch (CONTRIBUTING says it is
  unused) and an unmerged `claude/lux-grid-improvements-yr935b` branch; owner
  to decide whether to delete them.
- Lessons: 20261030-agents-md-drift, 20261030-no-shipped-limits,
  20261030-editable-install, 20261030-reference-documents.
