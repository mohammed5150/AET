# SDS-004 – Asset Engine: Asset Registry Import

> **Revision A** — §5.1 extended and §5.3 added after SDS-005 validation
> flagged 2,215 unclassified assets in the AUH export. Classification now
> covers fitting shorthands, CCRs, mast/flood lighting, obstruction and
> traffic lights, and falls back to circuit-family evidence in the asset
> name when the class column is unusable.

## 1. Purpose

This document specifies the first functional increment of the **Asset
Engine** (SDS-002 §8.6): importing an airport's asset registry from a
spreadsheet export into the AET asset domain, with classification and
circuit derivation. It is grounded in the AUH total-asset registry export
(33,865 assets, 141 asset classes, 8 main areas).

Drawing-based asset derivation (the `AssetExtractor` path) remains in place
and is unchanged; registry import is a second, complementary source of
assets, as anticipated by SDS-002's importer plugin category (§10.2).

## 2. Scope

SDS-004 covers:

- XLSX asset-registry reading behind a stable reader interface
- Column mapping with validation against the registry schema
- Normalization of registry rows into `Asset` records
- Asset classification (asset type) and circuit derivation from names
- A new application use case: import asset registry
- Reporting extension: asset counts by type
- Row-level fault tolerance, error handling, tests

SDS-004 does not cover:

- Drawing-vs-registry cross-validation rules (future SDS)
- Registry write-back or synchronization
- Coordinate transformation between UTM and drawing space

## 3. Registry Schema

The supported input is an XLSX workbook whose first worksheet (or a
worksheet named `Assets`) has a header row containing at least:

| Column | Meaning | Required |
| --- | --- | --- |
| `name` | Asset name / tag (e.g. `TCC102-01/067`, `HH.E4.035`) | yes |
| `assetClass` | Asset class / fitting spec (e.g. `ADB-BI-GG-S-INSET-8IN-2x40W`, `AGL PIT`) | yes |
| `mainArea` | Main airfield area (e.g. `ST`, `NT`, `MTA`, `AUX`) | yes |
| `subArea` | Sub-area / zone | no |
| `utmZone`, `utmE`, `utmN` | UTM location | no |
| `id` | Registry record id | no |
| `serialNumber`, `specialInstructions`, `genericText1..3`, `identifier` | Passthrough metadata | no |

Column mapping is configurable (a `RegistryColumnMap`); the defaults match
the AUH export headers above. A missing required column fails the import
with `INPUT_ERROR` naming the missing columns.

## 4. Normalization Rules

Each registry row becomes one `Asset`:

- `name` ← `name` (stripped); rows with an empty name are skipped and
  counted (§6)
- `asset_type` ← classification of `assetClass` (§5.1)
- `location` ← `{"utm_zone", "utm_e", "utm_n"}` as strings when present
- `attributes` ← `asset_class`, `main_area`, `sub_area`, `registry_id`,
  and any non-empty passthrough columns (snake_case keys); plus derived
  `circuit` and `circuit_family` when the name yields them (§5.2)
- `snapshot_id` ← `""` (registry assets derive from no drawing snapshot);
  provenance is carried by `attributes["registry_input_id"]` referencing
  the registered `SourceInput` of the registry file

## 5. Classification

### 5.1 Asset type

Derived from `assetClass` by first-match rules (defaults below,
overridable by the caller):

| Rule (case-insensitive) | asset_type |
| --- | --- |
| equals `AGL PIT` | `agl-pit` |
| contains `INSET` or `ELEV` | `light-fitting` |
| starts with `TWE-in` or `STB-in` (edge / stop-bar shorthand) | `light-fitting` |
| starts with `TCL-` or `LIL_` (centreline / lead-in shorthand) | `light-fitting` |
| equals `RGL` or `STL` | `light-fitting` |
| starts with `SGN`, or equals `SG` | `sign` |
| starts with `RRM` | `rrm` |
| contains `NBASE`/`EBASE`, or starts with `Base`/`CRBLK` | `base` |
| equals `Lightpoles` | `lightpole` |
| starts with `CCR-` | `ccr` |
| starts with `High Mast` | `high-mast` |
| contains `Streetlight` | `streetlight` |
| equals `Apron Stand` (stand floodlight arrays) | `apron-floodlight` |
| contains `Obstruction` | `obstruction-light` |
| starts with `TRL` | `traffic-light` |
| equals `WDI` | `wdi` |
| starts with `TRA`, `FCU`, `RRS`, or `LVO` (auxiliary crossing/access equipment) | `extra-asset` |
| otherwise | name-based fallback (§5.3), else `other` |

### 5.2 Circuit derivation

The asset name's prefix — the characters before the first `.` or `-` —
is parsed as `<FAMILY><DESIGNATOR>` where FAMILY is the leading run of
letters (e.g. `TCC102` → family `TCC`, circuit `TCC102`; `SBC13L` →
family `SBC`, circuit `SBC13L`; `HH` → family `HH`, no designator). When
the prefix contains no letters, no circuit attributes are set.

### 5.3 Name-based classification fallback

Registry exports contain rows whose class column is unusable (`Generic`,
`*U`, damaged text) while the asset name still follows the circuit naming
grammar. When class-based rules yield no match, the circuit family parsed
from the name (§5.2) classifies the asset:

| Family prefix | asset_type |
| --- | --- |
| `TCC`, `TEC`, `SBC`, `LIC`, `RCC`, `REC`, `RGC` | `light-fitting` |
| `SGC` | `sign` |
| `HH` | `agl-pit` |

Assets that neither path classifies remain `other` and are surfaced by
the SDS-005 `agl.asset.classification` rule. Auxiliary crossing/access
equipment (`TRA`, `FCU_1`, `RRS`, `LVO*`) is classified `extra-asset` —
registry-tracked equipment outside the core AGL taxonomy.

## 6. Fault Tolerance and Error Handling

1. Missing file, unreadable workbook, or missing required columns →
   `INPUT_ERROR` outcome with remediation; nothing is imported.
2. Row-level failures (empty name, unparseable cells) are skipped,
   logged at WARN with the row number, and counted; the import outcome
   message reports imported and skipped counts.
3. The import is transactional in effect: assets are persisted only when
   the read succeeds as a whole.

## 7. Application and Presentation

- New use case `import_asset_registry(project_id, path)`: registers the
  registry file as a `SourceInput` (via the ingestion engine, hash and
  format captured), reads and normalizes rows, persists assets, and
  audit-logs the import.
- `aet run` gains `--assets <file.xlsx>`, importing the registry after
  drawing processing so the report covers both.
- The project report gains an **Assets by Type** section with counts per
  `asset_type`.

## 8. Dependencies

- `openpyxl >= 3.1` becomes a runtime dependency (XLSX reading).

## 9. Acceptance Criteria

1. Importing a registry XLSX with the §3 schema yields persisted assets
   with the §4 fields, §5 classification, and circuit attributes.
2. A registry missing required columns fails with `INPUT_ERROR` naming
   them; a missing file fails with `INPUT_ERROR`.
3. Rows with empty names are skipped and counted, not fatal.
4. `import_asset_registry` on an unknown project fails with
   `WORKFLOW_ERROR`.
5. The report shows asset counts by type after an import.
6. The AUH total-asset export (33,865 rows) imports without error.
7. All behavior is covered by tests; `pytest`, `ruff`, and `black` pass.

Registry exports contain operational airport data: they must not be
committed to the repository. Tests use synthetic fixtures.
