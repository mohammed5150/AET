# SDS-012 – AGL Engineering Validation Rules

## 1. Purpose

This document specifies validation rules that check **the airfield**, rather
than the quality of the import.

Every rule shipped so far is data hygiene: are coordinates present, is each
asset classified, are names unique, did the two sources agree. Useful, but
none of it is engineering. SDS-012 adds the first two rules that assess the
installation itself — how far apart fittings sit on a circuit, and how much
load a circuit carries.

## 2. Dependencies

- **SDS-009** — numeric coordinates, so a separation is measurable.
- **SDS-010** — derived assets carrying circuit attributes identical to those
  the registry produces, so a circuit means the same thing from either source.
- **SDS-004** — the circuit families that identify a fitting's *function*
  (`TCC` taxiway centreline, `SBC` stop bar, `REC` runway edge, and so on).
  Asset type alone cannot distinguish them: all are `light-fitting`.

## 3. Scope

SDS-012 covers:

- Spacing between adjacent fittings on a circuit
- Connected electrical load per circuit
- Parsing load and regulator ratings out of asset class designations

SDS-012 does **not** cover, and §8 explains why:

- Sign placement relative to holding positions
- Any claim of ICAO Annex 14 conformance
- Circuit ordering or cable routing

## 4. No Regulatory Limit Is Shipped As A Default

**This is the central constraint of this increment.**

Spacing and loading limits come from ICAO Annex 14, from the aerodrome's own
design standards, and from the approach category and geometry of the surface
concerned. They are not a single number. Taxiway centreline spacing differs
between straights and curves, and with curve radius; runway centreline spacing
differs by approach category; loading margins differ by regulator type and
installation practice.

A tool that hardcoded one value from memory would be asserting a safety
threshold it cannot vouch for, in a form that looks authoritative because it
came out of software. An engineer could reasonably read a passing check as
confirmation of compliance.

Therefore:

1. Both rules ship with **empty** limit sets.
2. With no limits configured, a rule performs no check and says so in a
   passing INFO finding — it never silently passes.
3. Neither rule is in the standard pack (§7).

### 4.1 The example limit map

`EXAMPLE_SPACING_LIMITS` provides plausible starting values for the circuit
families the AUH and ZIA registries use. It is named "example", documented as
requiring verification, and **consumed by nothing** unless a caller passes it
in deliberately.

It exists so a project has somewhere to start, not so the tool has an opinion.

## 5. Spacing

### 5.0 Both rules are per circuit

Both rules group assets by their `circuit` attribute. An asset carrying no
circuit — a pit, a sign foundation, anything SDS-004's parser found no circuit
prefix on — belongs to no circuit and is therefore outside both rules by
construction, not silently dropped from a check that applied to it.

Counts in these findings are counts of *circuit-bearing* assets. A fitting
that should be on a circuit but carries none is a classification problem, and
`agl.asset.classification` is the rule that reports it.

### 5.1 Rule

`agl.spacing` groups assets by circuit, resolves each circuit's family to a
`SpacingLimit`, and measures every fitting's separation from its nearest
neighbour on the same circuit. A separation below the minimum or above the
maximum is a WARNING finding.

### 5.2 Nearest neighbour, and what it cannot see

Spacing is measured to the closest peer on the circuit, which needs no
ordering along the alignment. It detects:

- a near-zero gap — a fitting is duplicated
- an isolated fitting, far from every peer — likely mis-tagged onto the wrong
  circuit, or the last fitting of a run that has drifted

**It does not detect a fitting missing from the middle of a run.** Given
fittings at 0, 15, 45 and 60 m with the one at 30 m absent, every remaining
fitting still has a peer 15 m away on its other side, so no measured
separation exceeds the nominal. This limitation is pinned by a test rather
than left to be rediscovered.

Detecting an interior gap requires ordering fittings along the alignment and
measuring *consecutive* separations. That needs the centreline geometry to
project against, and the normalized model does not represent which polyline
is a centreline — so ordering would have to be guessed. A later increment
that derives alignment geometry can add it; until then the rule reports what
it can actually measure, and this document says what it cannot.

### 5.3 What was not checked is reported

A circuit is not spacing-checked when its family has no configured limit, or
when fewer than two of its fittings have positions. A fitting is not checked
when no peer has a comparable position — the cross-zone case SDS-009 refuses
to measure.

All three are counted in a separate INFO finding. Silence would let an
unchecked circuit read as a compliant one.

## 6. Circuit Load

### 6.1 Where the load comes from

Registry exports encode a fitting's load in its class designation rather than
in a column: `ADB-BI-GG-S-INSET-8IN-2x40W` is an 80 W fitting,
`ADB-UNI-C-ELEV-150W` a 150 W one. Regulator ratings appear the same way —
`CCR-CRE-30KVA`. Reading them makes loading checkable against data every
export already carries.

The multiplied form is matched before the single form: `2x40W` contains
`40W`, so the naive order would read 80 W as 40 W.

### 6.2 Rule

`agl.circuit-load` sums the parsed load per circuit and compares it against a
configured per-circuit rating in watts. With no ratings configured it reports
the computed load per circuit as INFO and judges nothing.

### 6.3 An unread class is not a zero-watt fitting

A class stating no wattage is counted and reported, never treated as zero.

The direction matters: treating unread classes as zero **understates** the
total, which makes an overloaded circuit look compliant. That is the failure
mode worth engineering against, so the count of unread classes is a WARNING
rather than an aside.

### 6.4 Regulator ratings are parsed but not auto-assigned

`parse_regulator_rating_kva` reads a regulator's rating, but nothing maps a
regulator to the circuits it feeds. That mapping is not in the data — a `CCR`
asset's name does not reliably identify its circuits — so ratings are supplied
by the caller rather than inferred. Inferring the mapping would attach a real
rating to the wrong circuit, which is worse than having no rating.

## 7. Rules Are Opt-In

Neither rule is in `standard_rules()`. An unconfigured rule adds a
"not configured" line to every report without checking anything, and the
limits it needs are project-specific by §4.

`agl_engineering_rules(spacing_limits=..., circuit_ratings_w=...)` builds them
configured, for passing to `validate_project(rules=...)`.

Wiring project limits through the CLI needs a structured configuration file —
`AppConfig` is flat key–value and cannot express a per-family map — which is
its own increment.

## 8. Deliberately Not Implemented

**Sign placement relative to holding positions.** A sign's correctness depends
on its position relative to the holding position it serves, its facing, and
the taxiway geometry. The model represents none of those: holding positions
are not derived, and a sign's rotation is captured but its facing relative to
a taxiway is not. Implementing this would mean inventing the reference
geometry, and a placement check against invented geometry is worse than no
check.

**ICAO Annex 14 conformance.** Annex 14 covers far more than spacing and
loading, and conformance is a judgement against a specific edition, aerodrome
category, and approved deviations. No rule in this increment claims it, and
none is named for it. The two rules here check configured limits, and the
finding text says so.

## 9. Acceptance Criteria

SDS-012 is satisfied when:

1. `parse_load_watts` reads both the multiplied and single forms, prefers the
   multiplied one, and returns `None` for a designation stating no load.
2. `parse_regulator_rating_kva` reads a kVA rating, including a fractional
   one, and returns `None` when absent.
3. `agl.spacing` with no limits performs no check and reports that it did not.
4. With limits, it flags separations below the minimum and above the maximum,
   and passes those within.
5. Circuits with no configured family limit, with fewer than two located
   fittings, or with no comparable neighbour, are reported unchecked.
6. `agl.circuit-load` sums parsed load per circuit and flags a circuit
   exceeding its configured rating.
7. With no ratings configured, it reports load and judges nothing.
8. Assets whose class states no load are counted and reported, and never
   contribute zero silently.
9. Neither rule appears in `standard_rules()`.
10. All behavior above is covered by tests; `pytest`, `ruff`, `black`, and
    `mypy` pass.
