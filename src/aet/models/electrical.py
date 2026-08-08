"""Electrical properties parsed from asset class designations (SDS-012).

Pure domain logic. Registry exports encode a fitting's load and a regulator's
rating in the ``assetClass`` string rather than in their own columns —
``ADB-BI-GG-S-INSET-8IN-2x40W`` is an 80 W fitting, ``CCR-CRE-30KVA`` a 30 kVA
constant-current regulator. Reading them makes circuit loading checkable
without adding columns no export provides.
"""

from __future__ import annotations

import re

# "2x40W" before "40W": the multiplied form contains the single form, so
# trying the single one first would read 80 W as 40 W.
_MULTIPLIED_WATTS = re.compile(
    # Both the ASCII "x" and the multiplication sign appear in real exports.
    r"(\d+)\s*[x\u00d7]\s*(\d+(?:\.\d+)?)\s*W\b",
    re.IGNORECASE,
)
_SINGLE_WATTS = re.compile(r"(\d+(?:\.\d+)?)\s*W\b", re.IGNORECASE)
_KVA = re.compile(r"(\d+(?:\.\d+)?)\s*KVA\b", re.IGNORECASE)


def parse_load_watts(asset_class: str) -> float | None:
    """The connected load of a fitting in watts, or ``None`` if unstated.

    ``None`` means the designation carries no load, not that the load is
    zero — a circuit total built from unparsed classes would understate the
    real load, so callers must count what they could not read (SDS-012 §6.3).
    """
    multiplied = _MULTIPLIED_WATTS.search(asset_class)
    if multiplied:
        return float(multiplied.group(1)) * float(multiplied.group(2))
    single = _SINGLE_WATTS.search(asset_class)
    if single:
        return float(single.group(1))
    return None


def parse_regulator_rating_kva(asset_class: str) -> float | None:
    """The rating of a constant-current regulator in kVA, or ``None``."""
    match = _KVA.search(asset_class)
    return float(match.group(1)) if match else None
