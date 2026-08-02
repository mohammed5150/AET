# SDS-007 – Reporting: Artifact Persistence and Versioning

## 1. Purpose

This document specifies durable storage for generated report artifacts.
Reports currently exist only in in-memory repositories and on the CLI's
stdout; SDS-007 writes each rendered artifact to file storage with
version-aware naming, per the SDS-002 storage split (§9.4: file storage
for exported reports) and report versioning requirement (§9.2.6).

## 2. Scope

SDS-007 covers:

- An artifact store contract and filesystem implementation
- Report version numbering per project and report type
- Artifact location tracking on the report artifact record
- Use-case and CLI integration
- Error handling for storage failures

SDS-007 does not cover:

- PDF/spreadsheet output formats (formatter adapters, future SDS)
- Retention policies or cleanup
- Remote/object storage backends

## 3. Artifact Store Contract

An artifact store implements:

- `save(project, report, artifact) -> str` — persist one rendered
  artifact, returning its location string; raises
  `InfrastructureError` on storage failure.

### 3.1 Filesystem store

The default store writes below a base directory (default: the
`AppConfig.data_dir`, `output/`):

```
<base>/<project-slug>/<report_type>-v<version>.<ext>
```

- `project-slug` — project name lowercased, runs of non-alphanumerics
  collapsed to `-` (trimmed); falls back to the project id if empty
- `ext` — mapped from the artifact's format (`markdown` → `md`,
  otherwise the format name)
- Parent directories are created as needed; an existing file for the
  same version is overwritten (idempotent regeneration)

## 4. Report Versioning

`generate_report` assigns each new report a version one greater than the
number of previously persisted reports for the same project and report
type (first report: version 1). The version appears in the artifact
filename and the stored report record.

## 5. Application and Presentation

- `ApplicationService` accepts an artifact store (default: filesystem
  store at `output/`). After a successful generation, each artifact is
  saved, its `location` is recorded on the artifact record, and the save
  is audit-logged.
- Storage failures fail the use case with an `INFRASTRUCTURE_ERROR`
  outcome (SDS-002 §12.2.4); the report and artifacts are not persisted
  to the repositories in that case.
- The CLI prints the written location of each artifact instead of the
  full report body, keeping stdout readable; `--no-save` retains the
  previous print-to-stdout behavior.

## 6. Model Change

`ReportArtifact` gains `location: str = ""` — empty until persisted.

## 7. Acceptance Criteria

1. Generating a report writes one file per artifact under
   `<base>/<project-slug>/` with the §3.1 naming and records the
   location on the artifact.
2. Re-generating the same report type increments the version; both
   files exist afterwards.
3. A storage failure yields an `INFRASTRUCTURE_ERROR` outcome and no
   half-persisted repository records.
4. `aet run` prints artifact locations; `aet run --no-save` prints the
   report body and writes nothing.
5. `pytest`, `ruff`, and `black` pass.
