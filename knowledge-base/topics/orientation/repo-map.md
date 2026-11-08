---
id: 20261030-repo-map
title: Repository map
tags: [orientation, architecture]
created: 2026-10-30
updated: 2026-10-30
related: [20261030-run-checks, 20261030-agents-md-drift]
summary: Where each pipeline stage, model and service lives, with its governing SDS.
---

# Repository map

> Summary: Where each pipeline stage, model and service lives, with its governing SDS.

## Context
Open this before changing code, to find the module and the design document
that governs it. Descriptions are the first line of each module's docstring.
When a module is added, moved or renamed, update this table in the same change.

## Pipeline
ingestion → drawing interpretation → asset derivation → validation → reporting
([SDS-002](../../../docs/SDS/SDS-002-System-Architecture.md) §7), orchestrated by
`services/pipeline.py` and exposed through `services/use_cases.py` and `ui/cli.py`.

## Modules (`src/aet/`)

| Module | Purpose |
|---|---|
| `core/config.py` | Application configuration resolution (SDS-002 §6.1) |
| `core/discovery.py` | Plugin discovery from disk and entry points (SDS-014) |
| `core/errors.py` | Error taxonomy for expected failures (SDS-002 §12.2) |
| `core/logging.py` | Structured logging and audit events (SDS-002 §11) |
| `core/outcome.py` | Structured processing outcomes (SDS-002 §12.3) |
| `core/plugins.py` | Plugin contracts and controlled runtime (SDS-002 §10) |
| `models/asset.py` | Engineering asset models (SDS-002 §8.6, §9.2.4) |
| `models/drawing.py` | Normalized drawing models (SDS-002 §8.5, §9.2.3) |
| `models/electrical.py` | Electrical properties from asset class designations (SDS-012) |
| `models/geometry.py` | Surveyed coordinate model (SDS-009) |
| `models/project.py` | Project and source-input models (SDS-002 §9.2.1–2) |
| `models/reconciliation.py` | Drawing assets reconciled against a registry (SDS-011) |
| `models/reference.py` | Engineering reference library models (SDS-016) |
| `models/report.py` | Report models (SDS-002 §8.8, §9.2.6) |
| `models/validation.py` | Validation models (SDS-002 §8.7, §9.2.5) |
| `modules/ingestion/engine.py` | Source file discovery, registration, metadata (SDS-002 §8.4) |
| `modules/drawing_engine/engine.py` | Drawing interpretation and normalization (SDS-003) |
| `modules/drawing_engine/dxf.py` | DXF interpretation via ezdxf (SDS-003 §5–6, SDS-008) |
| `modules/drawing_engine/dwg.py` | DWG support via external conversion to DXF (SDS-006) |
| `modules/drawing_engine/registry.py` | Format-keyed interpreter registry (SDS-003 §4) |
| `modules/asset_engine/engine.py` | Asset derivation entry point (SDS-002 §8.6) |
| `modules/asset_engine/derivation.py` | Asset derivation from normalized drawings (SDS-010) |
| `modules/asset_engine/registry.py` | Asset registry import from XLSX (SDS-004) |
| `modules/validation_engine/engine.py` | Validation processing (SDS-002 §8.7) |
| `modules/validation_engine/rules.py` | Built-in standard rule pack (SDS-005, SDS-011) |
| `modules/validation_engine/agl_rules.py` | AGL engineering validation rules (SDS-012) |
| `modules/reporting_engine/engine.py` | Report composition and formatting (SDS-002 §8.8) |
| `modules/reporting_engine/store.py` | Report artifact persistence (SDS-007) |
| `services/persistence.py` | Repository abstractions, in-memory (SDS-002 §8.9, §9) |
| `services/sqlite.py` | SQLite-backed repositories (SDS-013) |
| `services/serialization.py` | Dataclass/document conversion for persistence (SDS-013) |
| `services/reference_library.py` | The engineering reference library (SDS-016) |
| `services/pipeline.py` | Processing pipeline orchestration (SDS-002 §7) |
| `services/use_cases.py` | Application use cases (SDS-002 §8.2) |
| `ui/cli.py` | CLI: `run`, `project`, `import`, `process`, `validate`, `report`, `version` (SDS-015) |
| `utils/hashing.py` | Content hashing for source provenance (SDS-002 §9.2) |
| `utils/ids.py` | Identifier and timestamp helpers |

## Tests
`tests/` mirrors `src/aet/`; end-to-end runs are in `tests/integration/`.

## Related
- [Running the checks](run-checks.md) — see-also: how to verify a change to any module above.
- [AGENTS.md drifted from the code](../lessons/agents-md-drift.md) — background: why this map is kept beside the code.
