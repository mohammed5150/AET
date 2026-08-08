# SDS-010 – Asset Derivation from Drawings

## 1. Purpose

This document specifies how the **Asset Engine** (SDS-002 §8.6) derives
engineering assets from a normalized drawing snapshot, replacing the
placeholder `NullAssetExtractor` that returned nothing.

Until now every asset in the system came from an XLSX registry import
(SDS-004). The drawing path read a DXF, produced a snapshot, and derived zero
assets — so the toolkit's premise, drawing in and assets out, was unimplemented.

## 2. Dependencies

SDS-010 builds directly on:

- **SDS-008** — block ATTRIB capture. An asset's identity lives in the block's
  attributes; without them a reference is only a position and a block name.
- **SDS-009** — numeric coordinates. A derived asset's position must be
  measurable to be worth deriving.
- **SDS-004** — the asset-type vocabulary and circuit parsing. Derived assets
  must be describable in the *same* terms as registry assets, or the two can
  never be compared.

## 3. Scope

SDS-010 covers:

- Selecting which drawing entities are asset candidates
- Classifying a candidate into an asset type, by a project-tunable rule table
- Naming, positioning, and attributing a derived asset
- Provenance from asset back to source entity and snapshot
- Counting and reporting what was not derived, and why

SDS-010 does **not** cover:

- Deriving asset **relations** (§7.3)
- Reconciling derived assets against an imported registry (future SDS)
- Inferring circuit topology or cable routing
- Interpreting geometry other than block references (§5.1)

## 4. Why Block References Only

In AGL drawings a physical asset — a fitting, sign, pit, base — is placed as a
**block reference**. The surrounding lines, polylines, arcs, and text are
geometry and annotation: pavement edges, cable routes, labels, leaders. They
describe context, not countable assets.

Deriving an asset per line would produce a number that looks like an asset
count and is not one. Block references are therefore the only candidates.

Text entities are *not* used to name nearby fittings in this increment.
Associating a label with a fitting by proximity requires a distance threshold
that varies by drawing scale and annotation style; guessing one would silently
mis-attribute labels. ATTRIB values (SDS-008) carry the same information
without a guess.

## 5. Candidate Selection

1. Only entities of type `insert` are candidates.
2. A reference this reader cannot see into is **not** derived:
   - `block_is_xref` — the referenced file was never loaded, so deriving an
     asset for it would invent one whose content is unknown
   - `block_nested_inserts` — the reference is a container placing further
     references, so it is not itself one asset

   Both are counted separately (§8). This is what SDS-008's flags are for:
   they exist so this stage can decline rather than guess.
3. A candidate matching no classification rule is **skipped and counted**, not
   recorded as an `other` asset.

### 5.1 Why unmatched references are skipped, not classified `other`

This is the one place SDS-010 deliberately diverges from SDS-004.

Every row in a registry export *is* an asset, so SDS-004 classifies an
unrecognised row as `other` and lets a validation rule flag it. A drawing is
different: it also contains title blocks, north arrows, grid bubbles, revision
stamps, detail callouts, and legend symbols, all as block references. Treating
those as `other` assets would bury the real ones and make every asset count
meaningless.

The consequence is accepted and made visible: an under-configured rule table
silently derives too *few* assets. §8 therefore requires the skipped count to
be reported, so "0 assets derived from 40,000 references" is legible as a
configuration problem rather than an empty drawing.

## 6. Classification

Classification uses a table of rules, each mapping a pattern to one asset type
from the SDS-004 vocabulary.

1. **Block name is tried before layer.** A block name names the thing itself; a
   layer names where it was drawn. `TCL_LIGHT` on layer `AGL-MISC` is a
   fitting; the block is the stronger signal.
2. Within each pass, rules are evaluated in order and the first match wins.
3. Patterns are case-insensitive regular expressions.

### 6.1 The default rule table is a starting point, not an answer

Block and layer naming is a project convention, not a standard. The built-in
table covers the conventions seen in the AUH and ZIA drawing sets, and will be
wrong for a drawing set that names things differently.

It is therefore deliberately conservative — a pattern broad enough to catch
every fitting in one project will match a north arrow in another, and a
phantom asset is worse than a missing one because it is not obviously wrong.
Callers supply their own table for their own drawings.

## 7. The Derived Asset

### 7.1 Identity

The asset name comes from the first present of a configurable list of preferred
ATTRIB tags (default `TAG`, `ASSET_TAG`, `NAME`, `ID`). When none is present,
the name falls back to `<block name>:<entity handle>`.

The handle is used rather than a running counter because it is stable across
reads of the same file: re-deriving the same drawing yields the same names, so
results are comparable between runs.

`attributes["name_source"]` records which was used — `attrib:<TAG>` or
`handle` — so an asset whose identity is positional rather than tagged is
distinguishable. A drawing asset with no tag cannot be reconciled against a
registry by name, and that limitation must be visible in the data.

### 7.2 Position

The block reference's insertion point becomes the asset's `Coordinate`.

**The UTM zone is not inferred.** A DXF states coordinates, not the projection
they are in. Airfield survey drawings are commonly drawn in UTM eastings and
northings, which is why a drawing position and a registry `utmE`/`utmN` line
up — but the file never says so. The zone therefore comes from an explicit
option and defaults to unknown (`""`).

This is deliberate and consistent with SDS-009 §5.2: an unknown zone stays
measurable, so spacing rules work, while a *stated* zone enables the cross-zone
refusal. Inventing a zone would manufacture exactly the confident-looking
nonsense SDS-009 refuses.

Drawing units are recorded in `attributes["drawing_units"]`. Units other than
metres or unitless are additionally flagged, because every distance downstream
is in metres: a drawing in millimetres yields positions a thousand times too
large, and that must be visible rather than inferred from implausible spacings.

### 7.3 Relations

No relations are derived. `AssetCollection.relations` is empty.

The relation worth having is electrical: which fittings share a series
circuit, in what order. That is a property of cable routing, which the
normalized model does not represent — the polylines that look like cable are
not distinguishable from pavement markings without further specification.
Deriving relations from circuit-name equality alone would assert an ordering
that was never read from the drawing.

### 7.4 Attributes and provenance

Each derived asset carries:

- `snapshot_id` — the snapshot it came from (registry assets leave this empty;
  this is the field that will let the two be compared)
- `source_entity_ids` — the normalized entity it came from
- `attributes["block_name"]`, `attributes["layer"]`, `attributes["handle"]`
- every captured `attr.<TAG>` from SDS-008, unchanged
- circuit attributes from SDS-004's `derive_circuit`, applied to the asset
  name, so a drawing asset and a registry asset on the same circuit carry
  identical `circuit` and `circuit_family` values

## 8. Reporting What Was Not Derived

The result carries counts of candidates that produced no asset:

- `skipped_unclassified` — matched no rule (§5.1)
- `skipped_unresolved` — xref or nested container (§5.2)

Both are logged and both appear in snapshot-independent result metadata. A
derivation that classifies nothing must be diagnosable without re-reading the
drawing.

## 9. Acceptance Criteria

SDS-010 is satisfied when:

1. A block reference matching a rule yields one asset with the rule's type,
   its ATTRIB values, its position as a `Coordinate`, and provenance to its
   source entity and snapshot.
2. A block name rule wins over a conflicting layer rule.
3. A reference matching no rule yields no asset and increments
   `skipped_unclassified`.
4. An xref reference and a nested-container reference yield no assets and
   increment `skipped_unresolved`.
5. Non-`insert` entities never yield assets.
6. An asset with a preferred ATTRIB tag is named from it, with
   `name_source` recording the tag; one without is named from block and
   handle, with `name_source` of `handle`, stably across re-derivation.
7. The UTM zone is empty unless configured, and a configured zone appears on
   every derived coordinate.
8. Drawing units are recorded, and non-metre units are flagged.
9. Circuit attributes match those SDS-004 derives for the same name.
10. `relations` is empty.
11. The default extractor of `AssetEngine` performs this derivation, so the
    `aet run` pipeline produces assets from a drawing.
12. All behavior above is covered by tests; `pytest`, `ruff`, `black`, and
    `mypy` pass.
