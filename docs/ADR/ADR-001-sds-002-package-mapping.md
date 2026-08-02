# ADR-001: Mapping SDS-002 Modules onto the SDS-001 Repository Layout

## Status

Accepted

## Context

SDS-002 §6.1 names twelve top-level modules (presentation, application,
domain, ingestion, drawing-engine, asset-engine, validation-engine,
reporting-engine, persistence, plugin-runtime, logging/telemetry,
configuration). SDS-002 §14 sketches a `/src`-rooted layout for them, but
explicitly marks that section "directional only".

SDS-001 already established the repository layout around an `app/` package
(`core`, `ui`, `modules`, `services`, `models`, `utils`, `resources`), and
`pyproject.toml` packages that layout. Introducing a parallel `/src` tree
would create two competing structures.

## Decision

Keep the SDS-001 `app/` layout and map the SDS-002 modules onto it:

| SDS-002 module | Location |
| --- | --- |
| presentation | `app/ui/` |
| application (use cases, orchestration) | `app/services/use_cases.py`, `app/services/pipeline.py` |
| domain | `app/models/` |
| ingestion | `app/modules/ingestion/` |
| drawing-engine | `app/modules/drawing_engine/` |
| asset-engine | `app/modules/asset_engine/` |
| validation-engine | `app/modules/validation_engine/` |
| reporting-engine | `app/modules/reporting_engine/` |
| persistence | `app/services/persistence.py` |
| plugin-runtime | `app/core/plugins.py` |
| logging/telemetry | `app/core/logging.py` |
| configuration | `app/core/config.py` |

Cross-cutting error handling (`app/core/errors.py`) and the structured
outcome contract (`app/core/outcome.py`) also live in `app/core/`.

## Consequences

- One canonical package layout; SDS-002's dependency directions (§6.2) are
  preserved by convention: `ui → services → models`, engines depend on
  `models` and `core` only, and plugins depend on `app/core/plugins.py`
  contracts only.
- If a later SDS mandates the `/src` layout literally, the mapping above
  localizes the move to package renames.
