"""Built-in standard validation rule pack (SDS-005, SDS-011).

Each rule emits one aggregated finding per concern — passed or failed —
with a count and up to :data:`SAMPLE_LIMIT` sample references as evidence,
so reports stay readable at any project size.

:class:`ReconciliationRule` is the exception to one-finding-per-rule: it runs
one comparison and reports each way the two sources can disagree, since
recomputing the comparison per rule would repeat the whole match.
"""

from __future__ import annotations

from collections import Counter

from aet.models.reconciliation import (
    DEFAULT_POSITION_TOLERANCE_M,
    Reconciliation,
    match_key,
    partition_by_provenance,
    reconcile,
)
from aet.models.validation import Severity, ValidationResult
from aet.modules.validation_engine.engine import (
    ValidationContext,
    ValidationRule,
)

SAMPLE_LIMIT = 10


def _samples(names: list[str]) -> str:
    return ", ".join(names[:SAMPLE_LIMIT])


def aggregated_finding(
    rule_id: str,
    failures: list[str],
    total_checked: int,
    failure_severity: Severity,
    failure_message: str,
    passed_message: str,
) -> ValidationResult:
    """One finding summarising many failures, with a count and samples.

    Public because SDS-012's engineering rules build findings the same way;
    a helper shared across modules should not be private.
    """
    if failures:
        return ValidationResult(
            rule_id=rule_id,
            severity=failure_severity,
            passed=False,
            message=f"{failure_message} ({len(failures)} of {total_checked})",
            evidence={
                "count": str(len(failures)),
                "samples": _samples(failures),
            },
        )
    return ValidationResult(
        rule_id=rule_id,
        severity=Severity.INFO,
        passed=True,
        message=f"{passed_message} ({total_checked} checked)",
    )


class AssetLocationRule:
    """Every asset carries UTM coordinates (SDS-005 §4)."""

    rule_id = "agl.asset.location"
    description = "Every asset has UTM coordinates"

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        missing = [asset.name for asset in context.assets if asset.location is None]
        return [
            aggregated_finding(
                self.rule_id,
                missing,
                len(context.assets),
                Severity.WARNING,
                "Assets are missing UTM coordinates",
                "All assets have UTM coordinates",
            )
        ]


class AssetClassificationRule:
    """No asset is left unclassified (SDS-005 §4)."""

    rule_id = "agl.asset.classification"
    description = "Every asset resolves to a known asset type"

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        unclassified = [
            asset.name for asset in context.assets if asset.asset_type == "other"
        ]
        return [
            aggregated_finding(
                self.rule_id,
                unclassified,
                len(context.assets),
                Severity.WARNING,
                "Assets have an unclassified asset type",
                "All assets classified",
            )
        ]


class DuplicateAssetNameRule:
    """Asset names are unique within each source (SDS-005 §4, SDS-011 §8).

    Counted per provenance, not across the project. Once a drawing and a
    registry are both imported, every reconciled pair shares a name by
    definition, so counting the union would report each successful match as a
    duplicate — contradicting the reconciliation finding beside it.

    Names are compared as reconciliation compares them, so a name differing
    only in case is a duplicate here and ambiguous there, rather than passing
    one check and failing the other.
    """

    rule_id = "agl.asset.duplicate-names"
    description = "Asset names are unique within each source"

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        drawing, registry = partition_by_provenance(context.assets)
        duplicates: list[str] = []
        for label, group in (("drawing", drawing), ("registry", registry)):
            recorded: dict[str, str] = {}
            counts: Counter[str] = Counter()
            for asset in group:
                key = match_key(asset.name)
                counts[key] += 1
                recorded.setdefault(key, asset.name)
            duplicates.extend(
                f"{recorded[key]} (x{count} in {label})"
                for key, count in counts.items()
                if count > 1
            )
        return [
            aggregated_finding(
                self.rule_id,
                duplicates,
                len(context.assets),
                Severity.ERROR,
                "Duplicate asset names found within a source",
                "All asset names unique within each source",
            )
        ]


class SkippedEntitiesRule:
    """Drawings interpreted without skipped entities (SDS-005 §4)."""

    rule_id = "agl.drawing.skipped-entities"
    description = "No entities were skipped during interpretation"

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        skipped = [
            f"{snapshot.metadata.get('source_path', snapshot.snapshot_id)} "
            f"({snapshot.metadata['skipped_entities']} skipped)"
            for snapshot in context.snapshots
            if snapshot.metadata.get("skipped_entities", "0") not in ("", "0")
        ]
        return [
            aggregated_finding(
                self.rule_id,
                skipped,
                len(context.snapshots),
                Severity.WARNING,
                "Snapshots have skipped entities",
                "No skipped entities in any snapshot",
            )
        ]


class EmptyLayersRule:
    """Defined drawing layers actually carry entities (SDS-005 §4)."""

    rule_id = "agl.drawing.empty-layers"
    description = "No defined layer is empty"

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        empty = [
            f"{snapshot.metadata.get('source_path', snapshot.snapshot_id)}:"
            f"{layer.name}"
            for snapshot in context.snapshots
            for layer in snapshot.layers
            if layer.entity_count == 0
        ]
        total_layers = sum(len(snapshot.layers) for snapshot in context.snapshots)
        return [
            aggregated_finding(
                self.rule_id,
                empty,
                total_layers,
                Severity.INFO,
                "Defined layers carry no entities",
                "All defined layers carry entities",
            )
        ]


class ReconciliationRule:
    """Compares drawing-derived assets against the registry (SDS-011)."""

    rule_id = "agl.reconcile"
    description = "The drawing and the asset registry agree"

    def __init__(
        self, position_tolerance_m: float = DEFAULT_POSITION_TOLERANCE_M
    ) -> None:
        self._tolerance = position_tolerance_m

    def evaluate(self, context: ValidationContext) -> list[ValidationResult]:
        drawing, registry = partition_by_provenance(context.assets)
        result = reconcile(drawing, registry, position_tolerance_m=self._tolerance)
        if not result.applicable:
            # Comparing against an absent side would report every asset as
            # missing, which is noise rather than a finding (SDS-011 §7.1).
            return [
                ValidationResult(
                    rule_id=self.rule_id,
                    severity=Severity.INFO,
                    passed=True,
                    message=(
                        "Reconciliation not applicable: "
                        f"{result.drawing_total} drawing asset(s) and "
                        f"{result.registry_total} registry asset(s)"
                    ),
                )
            ]
        return [
            aggregated_finding(
                self.rule_id,
                result.ambiguous_names,
                result.drawing_total + result.registry_total,
                Severity.ERROR,
                "Asset names are duplicated, so they cannot be reconciled",
                "Every asset name is unique on both sides",
            ),
            aggregated_finding(
                self.rule_id,
                [pair.name for pair in result.type_mismatches],
                len(result.matched),
                Severity.ERROR,
                "Matched assets disagree on asset type",
                "Matched assets agree on asset type",
            ),
            aggregated_finding(
                self.rule_id,
                [asset.name for asset in result.missing_from_registry],
                result.drawing_total,
                Severity.WARNING,
                "Assets in the drawing are absent from the registry",
                "Every drawing asset is in the registry",
            ),
            aggregated_finding(
                self.rule_id,
                [asset.name for asset in result.missing_from_drawing],
                result.registry_total,
                Severity.WARNING,
                "Assets in the registry are absent from the drawing",
                "Every registry asset is in the drawing",
            ),
            aggregated_finding(
                self.rule_id,
                [
                    f"{pair.name} ({pair.distance:.2f} m)"
                    for pair in result.position_mismatches
                    if pair.distance is not None
                ],
                len(result.matched),
                Severity.WARNING,
                (
                    f"Matched assets are more than {self._tolerance:g} m apart "
                    f"between drawing and registry"
                ),
                f"Matched assets agree on position within {self._tolerance:g} m",
            ),
            # Reported so positions that were never compared cannot be mistaken
            # for positions that agreed (SDS-011 §7.2).
            aggregated_finding(
                self.rule_id,
                [pair.name for pair in result.unchecked_positions],
                len(result.matched),
                Severity.INFO,
                "Matched assets could not be compared by position",
                "Every matched asset was compared by position",
            ),
        ]


def reconciliation_summary(context: ValidationContext) -> Reconciliation:
    """The reconciliation for a context, for callers wanting the detail."""
    drawing, registry = partition_by_provenance(context.assets)
    return reconcile(drawing, registry)


def standard_rules() -> list[ValidationRule]:
    """The SDS-005 standard rule pack, in evaluation order."""
    return [
        AssetLocationRule(),
        AssetClassificationRule(),
        DuplicateAssetNameRule(),
        SkippedEntitiesRule(),
        EmptyLayersRule(),
        ReconciliationRule(),
    ]
