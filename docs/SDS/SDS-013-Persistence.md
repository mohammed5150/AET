# SDS-013 – SQLite Persistence

## 1. Purpose

This document specifies a durable store for project state, replacing the
in-memory repositories that lost everything at process exit.

Until now the toolkit could interpret a 72,000-entity drawing, derive assets
from it, reconcile them against a registry, and validate the result — and then
discard all of it. Every run started from nothing, so the CLI could only ever
be one hardcoded chain, and nothing could be inspected after the fact.

## 2. Scope

SDS-013 covers:

- A generic conversion between domain dataclasses and stored documents
- SQLite-backed repositories satisfying the existing `Repository` protocol
- Project-scoped reads served by an index
- A durable audit trail
- Selecting the store through configuration

SDS-013 does **not** cover:

- A normalized relational schema (§5)
- Schema migrations (§7)
- CLI subcommands that would use the store across invocations (§8)
- Concurrent access from multiple processes (§7)

## 3. The Protocol Boundary Was Not Real

`Repositories` documented itself as depending on the `Repository` protocol
"never on a concrete storage engine", while declaring every field as
`InMemoryRepository[T]`. The abstraction existed in the docstring only; no
alternative store could have been substituted without editing the bundle.

Fixed here: the bundle is typed to the protocol, and both stores build the
same bundle. This is the change that makes the rest of SDS-013 a substitution
rather than a rewrite.

## 4. Generic Conversion

Domain models are plain dataclasses, so conversion is written once rather
than nine times. `to_document` walks a dataclass into JSON-compatible
primitives; `from_document` rebuilds it by resolving each field's declared
type with `typing.get_type_hints`.

Handled: nested dataclasses (`Coordinate`, `DrawingLayer`, `DrawingEntity`),
`StrEnum` values, `datetime`, `X | None`, lists of dataclasses, and
`dict[str, object]` payloads such as entity geometry.

### 4.1 This depends on a lint decision made earlier

Resolving declared types at runtime requires the model modules to import their
types at runtime. SDS-012's lint configuration declined `flake8-type-checking`
for exactly this reason: it would have moved those imports into
`TYPE_CHECKING` blocks, where `get_type_hints` cannot see them, and this
conversion would fail at runtime with a `NameError` that no type checker would
have predicted.

### 4.2 A missing field keeps its default

A field absent from a stored document is not passed to the constructor, so it
takes its declared default. A model that gains a field can still read rows
written before that field existed, which is the minimum needed for the schema
to survive ordinary development without a migration system (§7).

## 5. Schema: Indexed Scope, Document Body

Each entity type gets a table of `(id, project_id, document)`, with
`project_id` indexed.

A fully normalized schema — a column per model field, nine schemas tracking
every model change — would buy SQL-level aggregation that no part of the
application performs. Every read the application makes is either by
identifier or scoped to a project.

So the indexed columns cover the queries that exist and the document covers
the rest. SDS-002 §9.5 requires that migration to a larger engine not break
application contracts; because the contract is the `Repository` protocol
rather than the schema, a normalized store can replace this one without
touching a caller.

### 5.1 Scoped reads are a lookup, not a scan

`list_for_project` uses the index. The in-memory store answers the same
question by scanning every entity, which was acceptable at hundreds of assets
and is not at tens of thousands — the AUH registry alone is 33,865 rows, and
the application scopes by project on every validation and every report.

An entity with no project of its own — an asset relation, a validation
finding, a report artifact — has no scope column, and its scoped read falls
back to filtering. Those are reached through their parent, so the index would
have nothing to serve.

## 6. Failures Are Infrastructure Errors

Every database operation is wrapped so a `sqlite3.Error` becomes an
`INFRASTRUCTURE_ERROR` with remediation, per SDS-002 §12.2, rather than a
driver exception crossing a module boundary. Opening an unusable path fails
the same way, at startup, with the path named.

## 7. Deliberately Not Included

**Migrations.** Tables are created if absent and a missing field falls back to
its default (§4.2), which covers additive change. A field being removed,
renamed, or retyped needs a migration system, and building one before any
schema has shipped would be speculative.

**Concurrent writers.** Each connection commits per write, and SQLite locks
per write, so two processes will contend. Nothing in the toolkit runs
concurrently today; a workload that does needs a connection strategy chosen
against its actual contention, not guessed at now.

## 8. What This Unblocks

The CLI is a single hardcoded chain because a second invocation had no way to
see what the first produced. With a database given, `aet run` writes state a
later command can read — so separate `import`, `validate`, and `report`
subcommands become implementable. That is the next increment, not this one.

## 9. Acceptance Criteria

SDS-013 is satisfied when:

1. Every domain model round-trips through `to_document`/`from_document`
   unchanged, including nested dataclasses, enums, datetimes, optional
   coordinates, and untyped geometry payloads.
2. A document missing a field yields an instance carrying that field's
   default.
3. `Repositories` is typed to the `Repository` protocol, and both stores
   build the same bundle.
4. A SQLite repository supports `add`, `get`, and `list` with the same
   semantics as the in-memory one, including replacing an entity re-added
   under the same identifier.
5. Entities written by one connection are readable by another, so state
   survives process exit.
6. `list_for_project` returns only that project's entities, for both scoped
   and unscoped tables.
7. Audit events persist and read back in order.
8. A database failure surfaces as `INFRASTRUCTURE_ERROR` with remediation.
9. `--database` and `AET_DATABASE` select the store; without either, the
   in-memory store is used and nothing is written.
10. All behavior above is covered by tests; `pytest`, `ruff`, `black`, and
    `mypy` pass.
