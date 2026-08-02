# SDS-003 – Drawing Engine: DXF Interpretation

## 1. Purpose

This document specifies the first functional increment of the **Drawing
Engine** defined architecturally in SDS-002 §8.5: replacing the placeholder
interpretation strategy with real drawing interpretation for **DXF** source
files, format-aware interpreter selection, and an enriched normalized drawing
model.

## 2. Scope

SDS-003 covers:

- Source format detection at ingestion time
- Format-aware interpreter selection (interpreter registry)
- DXF interpretation into the normalized drawing model
- Normalized geometry representation for downstream asset derivation
- Entity-level fault tolerance and error handling
- Handling of unsupported formats (including binary DWG)
- Tests and observability for the above

SDS-003 does **not** cover:

- Asset derivation rules (future SDS)
- Validation rules (future SDS)
- Binary DWG parsing (requires external conversion; see §7)
- 3D geometry fidelity beyond captured coordinates

## 3. Format Support

1. **DXF** (Drawing Exchange Format) is the supported interpretation format
   in this increment, read via the `ezdxf` library (both ASCII and binary
   DXF as supported by `ezdxf`).
2. Format identity is detected from the file extension at ingestion time and
   recorded on the `SourceInput` as `file_format` (lowercase, e.g. `"dxf"`,
   `"dwg"`; empty string when unknown).
3. Interpretation of a format with no registered interpreter fails with an
   `INPUT_ERROR` outcome and a remediation hint. For `"dwg"` specifically,
   the remediation must direct the user to convert the file to DXF.

## 4. Interpreter Selection

1. The drawing engine selects an interpreter from an **interpreter
   registry** keyed by format identity.
2. The registry is seeded with the built-in DXF interpreter and accepts
   additional registrations, including drawing-interpreter plugins
   (SDS-002 §10.2) whose extensions declare `supported_formats`.
3. An explicitly injected interpreter (constructor argument) bypasses the
   registry entirely; this preserves testability and SDS-002's strategy
   contract.

## 5. Normalized Drawing Model

### 5.1 Entities

Each interpreted drawing entity is normalized to a `DrawingEntity` with:

- `entity_type`: the DXF type name in lowercase (`line`, `lwpolyline`,
  `circle`, `arc`, `insert`, `text`, `mtext`, `point`, `polyline`)
- `layer`: source layer name
- `geometry`: numeric geometry payload; points are `[x, y]` pairs in
  drawing units:
  - `line`: `{"points": [start, end]}`
  - `lwpolyline`/`polyline`: `{"points": [...], "closed": bool}`
  - `circle`: `{"center": [x, y], "radius": r}`
  - `arc`: `{"center": [x, y], "radius": r, "start_angle": a1, "end_angle": a2}`
  - `insert` (block reference): `{"position": [x, y], "rotation": deg}`
  - `text`/`mtext`: `{"position": [x, y]}`
  - `point`: `{"position": [x, y]}`
- `attributes`: string metadata; must include the block `name` for
  `insert` entities and the text `content` for `text`/`mtext` entities.
- `geometry_ref`: the source entity handle from the DXF file, preserving
  provenance to the original drawing object.

Entity types outside this list are counted but not normalized (see §6).

### 5.2 Layers

Every layer defined in the drawing is represented as a `DrawingLayer` with
its name and the count of normalized entities on it — including layers with
zero entities, so downstream rules can detect empty expected layers.

### 5.3 Snapshot metadata

The `DrawingSnapshot.metadata` must include:

- `source_path`, `source_hash` (provenance, as today)
- `dxf_version`: DXF version string reported by the reader
- `units`: INSUNITS header value as a string (`"0"` when absent)
- `entity_count`: number of normalized entities
- `skipped_entities`: number of source entities not normalized

## 6. Fault Tolerance and Error Handling

1. **File-level failures** — a missing, corrupt, or structurally unreadable
   DXF file fails interpretation with an `INPUT_ERROR` outcome carrying a
   remediation hint. The pipeline stage fails; no snapshot is produced.
2. **Entity-level failures** — an entity that cannot be normalized (missing
   geometry, conversion error) is skipped: the failure is logged at WARN
   with the entity handle, `skipped_entities` is incremented, and
   interpretation continues. A drawing whose entities all fail still yields
   a valid (possibly empty) snapshot.
3. All failures follow the SDS-002 §12.3 structured-outcome contract.

## 7. DWG Position

Binary DWG is a proprietary format; parsing it natively is out of scope.
Registered `.dwg` inputs are accepted at ingestion (registration is
format-agnostic) but interpretation fails with `INPUT_ERROR` and remediation
directing conversion to DXF. A future SDS may integrate an external
DWG-to-DXF converter behind the ingestion adapter.

## 8. Observability

- Interpreter selection, per-file entity/skip counts, and file-level
  failures are logged through the structured logging API with stage
  `interpretation` and the pipeline correlation ID.
- Skipped entities are visible both in logs (WARN, with handle) and in
  snapshot metadata (`skipped_entities`).

## 9. Dependencies

- `ezdxf >= 1.3` becomes a runtime dependency of the `aet` package.

## 10. Acceptance Criteria

SDS-003 is satisfied when:

1. Importing and processing a DXF file produces a snapshot whose layers,
   entities, geometry, and metadata match §5 for all entity types listed.
2. A `.dwg` (or other unsupported) input fails interpretation with
   `INPUT_ERROR` and a conversion remediation hint.
3. A corrupt `.dxf` file fails interpretation with `INPUT_ERROR` without
   crashing the pipeline; unaffected sources still process.
4. Unsupported entity types and per-entity conversion failures are skipped
   and counted, not fatal.
5. `SourceInput.file_format` is populated at ingestion for all inputs.
6. Drawing-interpreter plugins can register additional formats through the
   plugin runtime and are selected by the registry.
7. All behavior above is covered by tests; `pytest`, `ruff`, and `black`
   pass.
