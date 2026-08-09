# ADR-003: Controlled Reference Documents Live Outside the Repository

## Status

Accepted. Records the repository-structure half of
[SDS-016](../SDS/SDS-016-Engineering-Reference-and-Standards-Architecture.md);
the domain and persistence decisions are in that document.

## Context

SDS-016 gives AET a catalogue of the authoritative documents its engineering
criteria will be traceable to — ICAO Annexes and manuals, UAE GCAA regulations,
AMC and GM, safety decisions, EASA and FAA material, aerodrome design
standards, manufacturers' manuals, project specifications.

The obvious next step is the wrong one. A `docs/Reference/` tree holding the
PDFs would make the toolkit self-contained and every citation directly
checkable, and it would also republish other people's copyrighted work from a
GitHub repository. ICAO documents are sold. GCAA material is published under
terms that are not "copy this anywhere". An aerodrome's own design standard is
frequently commercially confidential, and a project specification usually is.

The repository cannot tell these apart by looking at a file, and a mistake is
not recoverable: a document committed once stays in the git history after any
later deletion.

A second consideration points the same way. Engineers already hold these
documents, on controlled network shares under document control. A copy in a
git repository would be a second, unversioned, uncontrolled copy that drifts
from the controlled one — which is worse for engineering than having no copy.

## Decision

**AET records where a reference document is. It never holds one.**

Concretely:

1. The reference library stores metadata only: authority, number, edition,
   revision, dates, status, licence position, an official URL, and a local
   path. Nothing in the codebase opens the file at that path, downloads from
   that URL, parses document content, or embeds it.

2. Controlled documents live outside the working tree, on whatever controlled
   storage the operator already uses. `local_reference_path` points there and
   is expected to differ between machines.

3. `docs/Reference/` exists to document the recommended layout and to guard
   against accident. Its `.gitignore` refuses document binaries — PDF, Office
   formats, archives — so a controlled document dropped into the tree while
   working cannot be committed by mistake. The recommended per-authority
   subtree (`AGL/ICAO/`, `AGL/UAE_GCAA/`, `AGL/FAA/`, `AGL/EASA/`,
   `AGL/Airport_Specific/`, `AGL/Other/`) is described there and created by
   the operator on their own storage; empty placeholder directories are not
   committed.

4. Where a document genuinely is freely redistributable, that is recorded
   explicitly — `PUBLIC_OFFICIAL` source, `PUBLIC` licence, `OPEN` access —
   and only then does `ReferenceSource.redistributable` answer true. The
   default position for an uncharacterised document is restricted.

## Consequences

**Positive**

- The repository cannot redistribute copyrighted material, because it holds
  none, and the `.gitignore` makes doing so by accident hard.
- A system that never reads the document cannot leak it, cannot be made to
  fetch an attacker-supplied URL, and cannot be made to read an
  attacker-supplied path (SDS-016 §14).
- The controlled copy under the operator's own document control stays the only
  copy, so it cannot drift from a second one.
- The catalogue works for documents AET could never hold — restricted
  aerodrome standards, confidential project specifications — because metadata
  is enough to cite them.

**Negative**

- A citation cannot be verified from a clean checkout. Following one requires
  access to the document through its usual controlled channel, which is the
  same access an engineer needs to do the work.
- `local_reference_path` is machine-specific, so a catalogue shared between
  operators carries paths that may not resolve. Authority, number, edition,
  and revision identify the document regardless; the path is a convenience.

**Neutral**

- `docs/Reference/` holds a README and a `.gitignore` and no document tree.
  The structure sketched in the README is a recommendation for the operator's
  storage, not a set of empty directories in version control.
