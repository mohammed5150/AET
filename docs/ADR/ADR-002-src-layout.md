# ADR-002: Move the Package to a `src/` Layout

## Status

Accepted. Supersedes [ADR-001](ADR-001-sds-002-package-mapping.md)'s choice of
a repository-root `app/` package; the SDS-002 module mapping that ADR-001
records is otherwise unchanged.

## Context

ADR-001 kept the SDS-001 `app/` package at the repository root and declined
the `/src`-rooted layout sketched in SDS-002 §14, on the grounds that §14 is
marked "directional only" and that a parallel `/src` tree would create two
competing structures. That reasoning held while the package was named `app`
and there was no installed distribution to confuse it with.

Two problems emerged as the project grew a console script and a test suite:

1. **The working tree shadowed the installed package.** With `app/` at the
   root, `import app` resolves to the working tree whenever the interpreter
   starts there — which is always, for `pytest` and for `aet`. Tests
   therefore never exercised the installed distribution, so a packaging fault
   (a module missing from the wheel, a missing `py.typed`) could not fail a
   test run. This is the specific failure mode the `src/` layout exists to
   prevent.

2. **The import name did not match the distribution name.** The project is
   `aet` and the console script is `aet`, but the import package was `app` —
   a name generic enough to collide with any other root-level `app` package
   on the path.

## Decision

Move the package to `src/aet/`:

- the import name (`aet`) now matches the distribution name and the console
  script
- the working tree no longer contains an importable copy of the package, so
  `pytest` and `aet` both exercise the installed distribution
- `py.typed` ships with the package, so downstream consumers get the type
  information the codebase already carries

The internal structure ADR-001 established is preserved exactly — `core`,
`ui`, `modules`, `services`, `models`, `utils`, `resources` — so the SDS-002
module mapping in ADR-001 remains accurate with `app/` read as `src/aet/`.

The build backend moves from `setuptools` + `wheel` to `hatchling`, which
needs no `packages.find` configuration to describe a `src/` layout.

## Consequences

**Positive**

- A packaging fault now fails the test suite instead of hiding behind the
  working tree.
- `import aet` is unambiguous, and the name matches everywhere.
- Type information is published rather than merely present.

**Negative**

- Every import in the package and the test suite changed in one commit. The
  change is mechanical, but it is wide, and it invalidates outstanding
  branches that touch imports.
- Editable installs are now required to run the test suite: `pytest` from a
  clean checkout without `pip install -e .` no longer finds the package. This
  is the intended trade-off — it is the same constraint that makes the
  shadowing problem impossible — and CI installs the project explicitly.

**Neutral**

- SDS-002 §14's directional `/src` sketch and the repository layout now
  agree, where ADR-001 had them deliberately diverge.
