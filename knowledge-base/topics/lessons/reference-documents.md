---
id: 20261030-reference-documents
title: Reference documents are never committed
tags: [lesson, engineering, docs]
created: 2026-10-30
updated: 2026-10-30
related: [20261030-no-shipped-limits]
summary: AET records where a standard is, never the document itself.
---

# Reference documents are never committed

> Summary: AET records where a standard is, never the document itself.

## Context
[ADR-003](../../../docs/ADR/ADR-003-controlled-reference-documents.md): ICAO
documents are sold, GCAA material has its own terms, and aerodrome standards
and project specifications are often confidential. A file committed once
stays in git history after deletion.

## Rule
- Never add a PDF, scan or extract of a standard, manual or specification to
  the repository, including under `docs/Reference/`.
- Catalogue the document (edition, revision, effective date, applicability,
  location) in the reference library instead.
- If a user supplies such a document for a task, use it in the session and
  leave it out of commits.

## Related
- [No engineering limit is shipped](no-shipped-limits.md) — supports: criteria cite these catalogued documents.
