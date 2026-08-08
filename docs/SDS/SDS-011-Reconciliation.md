# SDS-011 – Drawing / Registry Reconciliation

## 1. Purpose

This document specifies the comparison of assets **derived from a drawing**
against assets **imported from an asset registry**, and the reporting of every
way the two can disagree.

This is the question an AGL engineer actually asks of the two sources: *the
drawing shows 412 centreline fittings on TCC102, the registry lists 398 — which
14 are missing, and are the rest where the registry says they are?* Neither
source alone can answer it.

## 2. Dependencies

- **SDS-010** — derived assets. Each carries the snapshot it came from, which
  is what distinguishes it from a registry asset.
- **SDS-009** — numeric coordinates, so a position disagreement can be
  measured rather than eyeballed.
- **SDS-004** — registry import, and the circuit parser both sides share so
  their attributes are directly comparable.

## 3. Placement

The comparison is **pure domain logic** in `aet.models.reconciliation`: a
function over `Asset` records with no engine machinery and no I/O.

It is not placed in the asset engine, because the validation engine needs it,
and SDS-002 §6.2 allows engines to depend on shared domain abstractions but not
on each other. Putting it in the domain layer keeps that direction intact — the
same reasoning that puts `Coordinate.distance_to` in `aet.models.geometry`
rather than in a rule.

## 4. Scope

SDS-011 covers:

- Distinguishing drawing assets from registry assets by provenance
- Matching them by name
- Classifying every disagreement, and reporting each as a validation finding

SDS-011 does **not** cover:

- Spatial matching of assets whose names differ (§5.5)
- Deciding which source is correct, or editing either to agree
- Reconciling anything other than assets

## 5. Matching

### 5.1 Provenance, not a flag

An asset came from a drawing when it carries a `snapshot_id`, and from a
registry when it does not. This is a consequence of how each is built —
SDS-010 §7.4 records the snapshot, SDS-004 leaves it empty — not a separate
marker that could disagree with reality.

### 5.2 Names are normalized before matching

Names are trimmed and case-folded for comparison. AGL tags are conventionally
upper case, and a tag differing only in case is the same tag recorded
inconsistently, not a different asset. Reporting uses the name as it was
actually recorded, so a case discrepancy stays visible in the output.

### 5.3 Duplicate names are reported, never resolved

A name appearing more than once on either side cannot be matched to a single
counterpart. Picking the first would assert an identification that was not in
the data, and the choice would be invisible in the result.

Such names are therefore reported as ambiguous and excluded from matching
entirely — they appear in neither the matched set nor either missing set, so no
count silently absorbs them.

### 5.4 Positions that cannot be compared are not treated as agreeing

A matched pair's separation is unavailable when either asset has no
coordinate, or when the two state **different** UTM zones — SDS-009 §5.2
refuses that measurement rather than returning a meaningless number.

Those pairs are counted separately (§7.2). Folding them into "positions agree"
would report a check that never ran as a check that passed.

### 5.5 Spatial matching is out of scope

Matching by nearest-neighbour would let an untagged drawing asset (SDS-010
§7.1 names those from the DXF handle) find its registry counterpart. It is
deliberately excluded: a nearest-neighbour match needs a radius, and at
typical AGL fitting spacing a radius wide enough to tolerate survey drift is
also wide enough to match the *adjacent* fitting. A wrong match is worse than
no match, because it reports a position discrepancy for two assets that were
never the same thing.

An untagged drawing asset therefore appears as missing from the registry, and
`name_source` on the asset says why it could not match.

## 6. Result

`Reconciliation` carries the two input totals and:

| Field | Meaning |
| --- | --- |
| `matched` | Pairs matched by name |
| `type_mismatches` | Matched pairs whose `asset_type` differs |
| `position_mismatches` | Matched pairs separated by more than the tolerance |
| `unchecked_positions` | Matched pairs whose positions cannot be compared |
| `missing_from_registry` | Drawing assets with no registry counterpart |
| `missing_from_drawing` | Registry assets with no drawing counterpart |
| `ambiguous_names` | Names duplicated on either side (§5.3) |

The three mismatch fields are **subsets of** `matched`, not disjoint buckets: a
pair the sources disagree about is still the same asset. Treating them as
disjoint would double-count.

The position tolerance defaults to 1.0 m and is configurable. Survey and
registry coordinates for one fitting agree closely; a project with looser
survey practice raises it.

## 7. Reporting

Reconciliation is surfaced through the validation engine as
`agl.reconcile`, so its findings reach reports by the existing path.

It emits one finding per category rather than one finding per rule — the
SDS-005 norm — because a single comparison answers all of them and running it
once per category would repeat the entire match.

### 7.1 Not applicable is stated, not implied

With assets from only one source, every asset on that side would be reported
missing from the other. That is noise, not a finding.

When either side is empty the rule emits a single passing INFO finding naming
both totals, so "reconciliation did not run" is distinguishable from
"reconciliation found nothing wrong".

### 7.2 Unchecked positions are their own finding

The count of matched pairs whose positions could not be compared is reported
as an INFO finding. A silent omission here would let an unverified position
read as a verified one.

## 8. Amendment to SDS-005 §4

`agl.asset.duplicate-names` counted names across every asset in the project.
That was correct while assets came from one source. Once a drawing and a
registry are both imported, **every reconciled pair shares a name by
definition**, so the union count reports each successful match as a duplicate —
directly contradicting the reconciliation finding printed beside it.

The rule now counts per provenance: uniqueness is required within the drawing
and within the registry, not across the two. It also compares names the way
reconciliation compares them (§5.2), so a name differing only in case is a
duplicate there and ambiguous here, rather than passing one check and failing
the other.

This was found by running the two rules together on real output, not by
reading them.

## 9. Acceptance Criteria

SDS-011 is satisfied when:

1. Assets are split by provenance: `snapshot_id` present means drawing.
2. A drawing asset and a registry asset with the same name are matched, with
   their separation in metres when both positions are comparable.
3. Matching ignores case and surrounding whitespace, while reporting uses the
   recorded name.
4. A name duplicated on either side is reported ambiguous and appears in no
   matched or missing set.
5. A matched pair whose types differ appears in `matched` **and**
   `type_mismatches`.
6. A matched pair separated by more than the tolerance appears in `matched`
   **and** `position_mismatches`; one within it appears only in `matched`.
7. A matched pair with a missing coordinate, or with conflicting UTM zones,
   appears in `unchecked_positions` and never in `position_mismatches`.
8. Drawing-only and registry-only assets appear in the correct missing set.
9. With either side empty, the rule emits exactly one passing INFO finding
   naming both totals.
10. With both sides present, the rule emits one finding per category of §6,
    each aggregated with a count and samples.
11. The rule is part of the standard pack, so `aet run` with both a drawing
    and a registry reports the comparison.
12. A drawing asset and its registry counterpart are not reported as
    duplicate names (§8), while duplicates within one source still are.
13. All behavior above is covered by tests; `pytest`, `ruff`, `black`, and
    `mypy` pass.
