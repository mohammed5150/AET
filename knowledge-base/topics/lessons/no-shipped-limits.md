---
id: 20261030-no-shipped-limits
title: No engineering limit is shipped
tags: [lesson, engineering, architecture]
created: 2026-10-30
updated: 2026-10-30
related: [20261030-reference-documents]
summary: Never hardcode a spacing, loading or photometric value; why, and where criteria belong.
---

# No engineering limit is shipped

> Summary: Never hardcode a spacing, loading or photometric value; why, and where criteria belong.

## Context
Applies to any change in `modules/validation_engine/` or anywhere a rule
compares a measured or derived value against a threshold.

## Details
[SDS-012](../../../docs/SDS/SDS-012-AGL-Engineering-Rules.md) §4 makes it the
central constraint: spacing and loading limits depend on ICAO Annex 14, the
aerodrome's own design standards, approach category and surface geometry. They
are not a single number. A hardcoded value would assert a safety threshold the
tool cannot vouch for.

## Rule
- Do not add a default limit, even "temporarily" or "for a test".
- A rule takes its criterion as an input that cites its source document,
  edition and clause through the reference library (SDS-016).
- Tests use clearly invented values and say so in the test name or comment.

## Related
- [Reference documents are never committed](reference-documents.md) — supports: where the cited source is recorded.
