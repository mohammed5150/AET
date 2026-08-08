# SDS-008 – Drawing Engine: Block Reference Fidelity

## 1. Purpose

This document specifies how the **Drawing Engine** (SDS-002 §8.5, SDS-003)
interprets DXF **block references**, so that the engineering payload AGL
drawings carry inside blocks survives interpretation, and so that a
reference whose content the reader cannot see is recorded rather than
mistaken for an empty one.

SDS-008 amends SDS-003 §5.1 and §5.3.

## 2. Motivation

In AGL drawings a light fitting, sign, or pit is placed as a **block
reference** (DXF `INSERT`), and the data that identifies it — circuit,
asset tag, fitting type — lives in the block's **ATTRIB** values, not in
the geometry. SDS-003 captured only the block name, position, and rotation,
so every attribute was discarded at the boundary. Asset derivation cannot
identify an asset from a position and a block name alone, which makes this
a prerequisite for the asset-derivation increment.

Two further cases were silently lossy:

- an `INSERT` whose block definition is an **external reference** (xref):
  the referenced file is not loaded, so its contents are absent
- an `INSERT` whose block definition **contains further `INSERT`s**: the
  reader normalizes the outer reference as one entity, not as the several
  fittings placed inside it

Both produced a snapshot that looked complete. Neither is interpreted by
this increment, but both must be visible.

## 3. Scope

SDS-008 covers:

- Capturing block ATTRIB tag/value pairs onto the normalized entity
- Namespacing captured attributes so drawing-supplied tags cannot collide
  with reader-supplied keys
- Recording block references whose content is unresolved (xref, nested)
- Snapshot-level counters for unresolved references

SDS-008 does **not** cover:

- Resolving or loading external reference files
- Exploding block definitions into their constituent entities (§6.2)
- Deriving assets from the captured attributes (future SDS)
- ATTDEF defaults on block *definitions* that carry no ATTRIB on the
  reference itself

## 4. Block Attribute Capture

1. For each `insert` entity, every ATTRIB attached to the reference is
   captured into `DrawingEntity.attributes`.
2. The key is the ATTRIB tag prefixed with `attr.`; the value is the
   ATTRIB text, as a string.
3. An ATTRIB with a blank tag is ignored.
4. A reference carrying no ATTRIBs gains no `attr.`-prefixed keys — absence
   is represented by absence, not by an empty value.

### 4.1 Why the tags are namespaced

Tags originate in the drawing, so they are outside the reader's control. A
block tagged `NAME` would otherwise overwrite the reader's own `name` key
and silently change the meaning of a field downstream code depends on. The
prefix keeps the two namespaces separable, and keeps captured attributes
enumerable (`key.startswith("attr.")`).

## 5. Normalized Model Amendments

### 5.1 Entity attributes (amends SDS-003 §5.1)

For `insert` entities, `attributes` must include:

- `name`: the referenced block name (unchanged from SDS-003)
- `attr.<TAG>`: one entry per ATTRIB on the reference (§4)
- `block_is_xref`: `"true"` when the referenced block is an external
  reference; absent otherwise
- `block_nested_inserts`: the number of `INSERT` entities in the referenced
  block's definition, when greater than zero; absent otherwise

### 5.2 Snapshot metadata (amends SDS-003 §5.3)

`DrawingSnapshot.metadata` gains:

- `xref_references`: count of normalized entities carrying `block_is_xref`
- `nested_block_references`: count of normalized entities carrying
  `block_nested_inserts`

Both are always present, and are `"0"` for a drawing with neither case.

## 6. Unresolved References

### 6.1 External references

An xref's content is not loaded by the reader, so entities defined inside
it never reach the snapshot. The reference itself is normalized as an
`insert` and flagged. A consumer that needs the referenced content must
either bind the xref before export or interpret the referenced file as its
own source input.

### 6.2 Nested block definitions

A block definition placing further references — a "typical" detail holding
several fittings — is normalized as the single outer reference. Exploding
it is deliberately **not** done here:

- explosion multiplies entity counts, so a count meaningful today would
  change meaning without the layer or provenance to explain why
- the outer block's identity is itself the classification signal for asset
  derivation; discarding it in favour of its constituent geometry loses
  information rather than gaining it

Recording the nested count instead lets the asset-derivation increment
decide per block, with the fact available rather than inferred.

## 7. Performance

Block definition facts (§5.1) are resolved **once per document** and looked
up per reference. A drawing may hold tens of thousands of references to a
few dozen definitions, so per-reference definition traversal is not
acceptable.

## 8. Observability

Unresolved-reference counts are visible in snapshot metadata (§5.2), so a
drawing whose content is partly invisible can be identified without
re-reading the source file.

## 9. Acceptance Criteria

SDS-008 is satisfied when:

1. A block reference carrying ATTRIBs yields one `attr.<TAG>` entry per
   ATTRIB, with the block name preserved under `name`.
2. A block reference carrying no ATTRIBs yields no `attr.`-prefixed keys.
3. A reference to an external reference block carries
   `block_is_xref="true"` and is counted in `xref_references`.
4. A reference to a block definition containing nested references carries
   `block_nested_inserts` with the correct count and is counted in
   `nested_block_references`; a reference to a flat block carries neither.
5. A drawing with no unresolved references reports `"0"` for both counters.
6. Block definition facts are resolved once per document, not once per
   reference.
7. All behavior above is covered by tests; `pytest`, `ruff`, and `black`
   pass.
