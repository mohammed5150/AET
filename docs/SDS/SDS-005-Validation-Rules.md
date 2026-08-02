# SDS-005 – Validation Engine: Standard Rule Pack

## 1. Purpose

This document specifies the first functional increment of the **Validation
Engine** (SDS-002 §8.7): a built-in pack of data-quality rules evaluated
over the project's imported assets (SDS-004) and interpreted drawings
(SDS-003), producing severity-based, evidence-backed findings.

## 2. Scope

SDS-005 covers:

- The standard rule pack (five rules, §4)
- The aggregation principle for findings (§3)
- Default rule wiring in the validate-project use case (§5)
- Tests and acceptance criteria

SDS-005 does not cover:

- Standards-based photometric or spacing rules (require survey-grade
  coordinates; future SDS)
- Drawing-vs-registry geometric cross-checks (blocked on a shared
  coordinate frame; future SDS)
- Rule configuration files

## 3. Aggregation Principle

Each rule emits **exactly one finding per run** — passed or failed — so
reports stay readable at any project size:

- `passed=True`, severity `info` when the rule holds, with a message
  stating what was checked
- `passed=False`, the rule's severity, when it fails, with a count and up
  to 10 sample references in `evidence` (`count`, `samples`)

## 4. Standard Rules

| rule_id | Severity on failure | Fails when |
| --- | --- | --- |
| `agl.asset.location` | `warning` | Any asset lacks `utm_e`/`utm_n` in its location |
| `agl.asset.classification` | `warning` | Any asset has `asset_type == "other"` (taxonomy gap) |
| `agl.asset.duplicate-names` | `error` | Two or more assets share a name |
| `agl.drawing.skipped-entities` | `warning` | Any snapshot's `skipped_entities` metadata is non-zero |
| `agl.drawing.empty-layers` | `info` | Any snapshot has layers defined with zero entities |

Rules evaluate the full `ValidationContext`; a rule with nothing to check
(e.g. no assets imported) passes with a message saying so.

## 5. Default Wiring

`validate_project(project_id, rules=None)` semantics:

- `rules=None` (default) → the standard rule pack runs
- `rules=[]` → no built-in rules (caller opts out)
- any explicit list → exactly those rules

Plugin-provided validation rules (SDS-002 §10.2) are appended in every
case, unchanged from SDS-002. The CLI `run` command uses the default and
therefore runs the standard pack.

## 6. Acceptance Criteria

1. Each rule produces a passed finding on clean data and a failed finding
   with count + samples on violating data.
2. Findings follow §3: one per rule per run, evidence capped at 10
   samples.
3. `rules=None` runs the standard pack; `rules=[]` runs none; plugin
   rules append in both cases.
4. The report's findings table shows rule IDs, severities, and statuses.
5. All behavior is covered by tests; `pytest`, `ruff`, and `black` pass.
