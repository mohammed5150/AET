# SDS-015 – CLI Subcommands

## 1. Purpose

This document specifies the command set that exposes the SDS-002 §8.2 use
cases individually, replacing a CLI that offered one fixed chain.

`ApplicationService` has always defined five use cases. `aet run` welded them
into a single sequence, so an operator could not import today and validate
tomorrow, re-run validation after changing a rule, or regenerate a report
without re-parsing the drawing.

## 2. Why This Comes After Persistence

The CLI was one chain because a second invocation had nothing to read. Every
use case needs the state the previous one produced, and until SDS-013 that
state died with the process.

The dependency is why these commands ship now and not earlier.

## 3. Commands

| Command | Use case |
| --- | --- |
| `aet project create NAME` | Create a project; prints its identifier |
| `aet project list` | Known projects and their asset counts |
| `aet import PROJECT [FILES…] [--registry XLSX]` | Register drawings and registries |
| `aet process PROJECT` | Interpret drawings and derive assets |
| `aet validate PROJECT` | Run the validation rules |
| `aet report PROJECT` | Generate a report |
| `aet run [FILES…]` | The existing one-shot chain, unchanged |

`aet run` keeps working exactly as before, with or without a database. An
operator who wants the old behaviour has not lost it.

## 4. A Stateful Command Refuses To Run Without A Store

Every command above except `run` and `version` requires a database.

Without one they would appear to work — `project create` would print an
identifier, and the next command would report the project missing. Refusing
up front, with a hint naming both `--database` and `aet run`, is the
difference between a clear error and a confusing one.

## 5. Addressing A Project

A project is named by identifier or by name.

Identifiers are generated, so requiring one would mean copying a 32-character
string between commands; a name is what an operator actually has. But names
are not unique, so an ambiguous name is **reported with the candidate
identifiers**, never resolved by taking the first match — silently acting on
the wrong project is the failure this avoids.

## 6. Source Role: A Latent Bug This Exposed

Splitting import from process revealed a defect `aet run` had always hidden.

`import_asset_registry` registers its workbook as a `SourceInput`, exactly as
a drawing import does, and `process_drawings` interpreted *every* registered
source. In `run` the registry was imported *after* processing, so the two
never met. Import a registry first, as the new command set allows, and
processing fails with `No interpreter registered for format 'xlsx'`.

`SourceInput` now carries a `SourceRole` — `drawing` or `registry` — and
processing interprets only drawings. The role is a property of why a file was
registered, which is knowledge the importing use case has and the pipeline
otherwise has to guess from a file extension.

Rows written before the field existed load with the default `drawing`, per
SDS-013 §4.2.

## 7. `validate` Signals Findings Through Its Exit Status

`aet validate` exits `2` when any rule fails, `0` when all pass, and `1` on an
error such as an unknown project.

A failing rule is not a failure of the command — the command worked, and the
airfield did not. A distinct status lets a pipeline gate on validation without
parsing output, while keeping "the tool broke" separable from "the tool found
something".

## 8. Acceptance Criteria

SDS-015 is satisfied when:

1. Create, import, process, validate, and report each run as separate
   invocations, each seeing what the previous one wrote.
2. Every stateful command refuses to run without a database, naming both the
   flag and `aet run` in its remediation.
3. `aet run` behaves exactly as before, with or without a database.
4. A project resolves by identifier and by name; an unknown name is reported
   with a hint, and an ambiguous one with the candidate identifiers.
5. A registry workbook is not interpreted as a drawing, and a project holding
   only a registry reports having no drawings to process.
6. `validate` exits 2 on any failing rule, 0 when all pass, 1 on error.
7. All behavior above is covered by tests; `pytest`, `ruff`, `black`, and
   `mypy` pass.
