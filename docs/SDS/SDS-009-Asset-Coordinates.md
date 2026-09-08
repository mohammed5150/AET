# SDS-009 – Typed Asset Coordinates

## 1. Purpose

This document specifies a **numeric coordinate model** for derived assets,
replacing the untyped string map that `Asset.location` previously carried.
Spatial validation — spacing between fittings, proximity of a sign to a
holding position, circuit routing distance — cannot be expressed against
coordinates held as text.

SDS-009 amends the asset model of SDS-002 §9.2.4 and the registry import of
SDS-004 §5.

## 2. Motivation

`Asset.location` was `dict[str, str]`, populated from the registry export as
`{"utm_zone": "40 N", "utm_e": "261833.45", "utm_n": "2703563.93"}`. Three
consequences followed:

1. Every consumer had to re-parse the ordinates, so parsing rules would be
   restated — differently — at each call site.
2. Nothing distinguished "no coordinate recorded" from "coordinate recorded
   as unusable text": both were a dict missing the expected keys.
3. No rule could measure a distance, which blocks the entire class of
   validation rules that carry engineering value.

## 3. Scope

SDS-009 covers:

- A `Coordinate` value type with numeric ordinates
- Distance measurement between coordinates, including cross-zone refusal
- Fallible parsing from registry text into a coordinate
- Preservation of ordinates that cannot be parsed
- Amendments to the asset model, registry import, and location rule

SDS-009 does **not** cover:

- Coordinate system transformation or re-projection between UTM zones
- Geodetic (ellipsoidal) distance; §5.2 is planar
- Coordinates on `DrawingEntity`, whose geometry is already numeric
  (SDS-003 §5.1)
- The spatial validation rules this model enables (future SDS)

## 4. Coordinate Model

`Coordinate` is an immutable value type with:

- `easting`: float, metres
- `northing`: float, metres
- `zone`: UTM zone identity as a string; `""` when unknown
- `elevation`: float in metres, or `None` when not surveyed

Immutability means a coordinate can be shared between an asset and a
validation finding without either being able to alter it.

## 5. Behavior

### 5.1 Asset location (amends SDS-002 §9.2.4)

`Asset.location` is `Coordinate | None`. `None` means the source recorded no
usable position. This is a single, unambiguous representation of "unknown",
replacing the several shapes an untyped map could take.

### 5.2 Distance

`Coordinate.distance_to` returns the planar distance in metres, ignoring
elevation. Airfield geometry is effectively planar at the scale these rules
operate on, and elevation is frequently unsurveyed.

Measuring between two **different** UTM zones raises a `PROCESSING_ERROR`
rather than returning a number. The arithmetic would succeed and produce a
value that looks like a distance while being meaningless; a rule silently
comparing across zones would report confident nonsense. An unknown zone
(`""`) on either side is permitted, so coordinates of unstated provenance
remain measurable.

Zones are compared after folding away case and internal whitespace, so
`"40 N"`, `"40N"`, and `"40n"` — the same zone as written by a registry
export, a CLI option, or a different operator — are recognised as one zone.
Without this, two coordinates in the same real zone but differently
formatted would spuriously fail as "different zones", degrading spacing
validation (SDS-012 §5.2) to "not comparable" for assets that are, in fact,
adjacent. The stored `zone` string itself is unchanged by this — only the
comparison is normalized — so raw provenance is still preserved.

### 5.3 Parsing

`parse_coordinate` builds a coordinate from survey values of any type and
returns `None` when the result would not be a usable position:

1. **Both ordinates are required.** A half-known position is not a
   position, so a missing or unparsable easting *or* northing yields `None`.
2. **Elevation is optional.** An unusable elevation leaves `elevation`
   unset; it does not discard a known planar position.
3. **Blank and non-numeric text are absent**, not zero.
4. **Non-finite values are absent.** `float()` accepts `"nan"`, `"inf"`, and
   `"-inf"`; a NaN ordinate would propagate through every subsequent
   comparison as a false negative instead of failing where it was read.
5. The zone is trimmed; `None` becomes `""`.

### 5.4 Registry import (amends SDS-004 §5)

The registry reader parses `utmE`/`utmN`/`utmZone` into a coordinate. When
the result is `None` but the export did carry ordinate text, the row is
**still imported** — an asset with an unusable position is a real asset —
and the raw values are preserved so the defect can be corrected at source:

- `attributes["utm_unparsed"]`: the raw easting and northing, `|`-separated
- `attributes["utm_zone"]`: the raw zone, when a zone was given without a
  usable position
- a WARN log record naming the row, the asset, and the offending values

This follows the row-level fault tolerance of SDS-004 §6: a bad cell
degrades one field, it does not reject the row.

### 5.5 Location rule (amends SDS-005 §4)

`agl.asset.location` reports assets whose `location` is `None`. The rule's
severity, aggregation, and sampling are unchanged.

## 6. Acceptance Criteria

SDS-009 is satisfied when:

1. `Asset.location` is a `Coordinate` when known and `None` when not.
2. Distance between two coordinates in the same zone, or where either zone
   is unknown, is the planar distance in metres and ignores elevation.
3. Distance across two different known zones raises `PROCESSING_ERROR` with
   remediation.
4. Distance between two coordinates in the *same* zone written with
   different case or whitespace (e.g. `"40 N"` vs `"40N"`) succeeds rather
   than raising a cross-zone error.
5. Parsing accepts survey text and numbers, and returns `None` when either
   ordinate is missing, blank, non-numeric, or non-finite.
6. Parsing keeps a known planar position when only the elevation is
   unusable.
7. A registry row with unusable ordinates is imported with `location` unset,
   its raw values preserved, and a WARN record naming the row.
8. `agl.asset.location` flags exactly the assets with no coordinate.
9. All behavior above is covered by tests; `pytest`, `ruff`, and `black`
   pass.
