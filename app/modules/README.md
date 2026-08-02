# Modules

Feature modules for AET — the processing engines of the DWG-to-report
pipeline (SDS-002 §7, §8):

- `ingestion/` — source file registration and metadata reading (§8.4)
- `drawing_engine/` — drawing interpretation and normalization (§8.5)
- `asset_engine/` — asset derivation from normalized drawings (§8.6)
- `validation_engine/` — rule evaluation with isolated failures (§8.7)
- `reporting_engine/` — report composition and output formatting (§8.8)

Each engine exposes a strategy/extension contract (`SourceReader`,
`DrawingInterpreter`, `AssetExtractor`, `ValidationRule`,
`ReportFormatter`) that plugins can implement via `app/core/plugins.py`.
