# SDS-006 – Drawing Engine: DWG Conversion Adapter

## 1. Purpose

This document specifies DWG support for the Drawing Engine by conversion:
binary DWG sources are converted to DXF through an external converter
adapter, then interpreted by the SDS-003 DXF interpreter. It replaces the
SDS-003 §7 position (reject `.dwg` outright) with a conversion pipeline
while keeping native DWG parsing out of scope.

## 2. Scope

SDS-006 covers:

- The converter adapter contract and backend auto-detection
- Two converter backends: ODA File Converter and GNU LibreDWG
- A DWG interpreter that converts, then delegates to the DXF interpreter
- Provenance metadata for converted drawings
- Error handling when no backend is available
- Tests (fake-converter units; self-skipping real-tool integration)

SDS-006 does not cover:

- Native DWG parsing
- Batch/watched-folder conversion
- Bundling or licensing of converter binaries

## 3. Converter Adapter Contract

A converter backend implements:

- `name` — stable identifier (`"oda"`, `"libredwg"`)
- `available() -> bool` — true when the backend's executable is usable in
  this environment
- `convert(dwg_path, output_dir) -> Path` — produce a DXF file; raises
  `InputError` for corrupt/unreadable DWG input, `ProcessingError` for
  converter execution failures

### 3.1 ODA File Converter backend

Runs the ODA File Converter executable (resolved from the
`ODA_FILE_CONVERTER` environment variable, else `ODAFileConverter` on
`PATH`) with its directory-based CLI (`<in> <out> <version> DXF 0 1
<filter>`), targeting `ACAD2018` DXF.

### 3.2 LibreDWG backend

Runs `dwg2dxf` (resolved from the `DWG2DXF` environment variable, else
`dwg2dxf` on `PATH`) as `dwg2dxf -o <out.dxf> <in.dwg>`.

## 4. DWG Interpretation Flow

1. The interpreter registry maps format `"dwg"` to a
   `DwgConversionInterpreter` holding an ordered backend chain
   (default: ODA, then LibreDWG).
2. On interpret, the first backend whose `available()` returns true is
   selected. If none is available, interpretation fails with
   `INPUT_ERROR` and remediation naming both install options and the
   manual-conversion fallback.
3. The DWG is converted into a temporary directory; the resulting DXF is
   interpreted by the SDS-003 `DxfInterpreter`; temporary files are
   removed afterwards.
4. The produced snapshot carries DWG provenance (§5). The converted DXF
   is transient — the snapshot is the durable artifact.

## 5. Provenance Metadata

The snapshot metadata of a converted drawing must record:

- `source_path` — the **original DWG path** (not the temporary DXF)
- `source_hash` — the registered DWG file hash
- `converter` — the backend `name` that performed the conversion
- all SDS-003 metadata (`dxf_version`, `units`, `entity_count`,
  `skipped_entities`) from the converted DXF

## 6. Error Handling

| Condition | Outcome |
| --- | --- |
| No backend available | `INPUT_ERROR`, remediation lists ODA File Converter, LibreDWG (`dwg2dxf`), and manual conversion |
| Converter exits non-zero or produces no DXF | `ProcessingError` with the converter's diagnostic output (truncated) |
| Corrupt DWG rejected by converter | `InputError` |
| Converted DXF unreadable | `INPUT_ERROR` (from the DXF interpreter) |

All failures surface as structured outcomes through the existing drawing
engine boundary (SDS-002 §12.3).

## 7. Acceptance Criteria

1. With a working backend (real or injected), `aet run project.dwg`
   interprets the drawing and the snapshot metadata satisfies §5.
2. With no backend available, interpreting a `.dwg` fails with
   `INPUT_ERROR` and the §6 remediation; the pipeline fails cleanly.
3. Backend selection honors chain order and skips unavailable backends.
4. Converter execution failures yield `ProcessingError` outcomes, not
   crashes.
5. Unit tests cover the flow with an injected fake converter; an
   integration test exercises a real backend and self-skips when none is
   installed.
6. `pytest`, `ruff`, and `black` pass.
