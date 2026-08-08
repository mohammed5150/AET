"""Built-in standard validation rule pack (SDS-005).

Each rule emits exactly one aggregated finding per run — passed or failed
— with a count and up to :data:`SAMPLE_LIMIT` sample references as
evidence, so reports stay readable at any project size.
"""

from __future__ import annotations

from collections import Counter

from app.models.validation import Severity, ValidationResult

SAMPLE_LIMIT = 10


def _samples(names: list[str]) -> str:
    return ", ".join(names[:SAMPLE_LIMIT])


def _finding(
    rule_id: str,
    failures: list[str],
    total_checked: int,
    failure_severity: Severity,
    failure_message: str,
    passed_message: str,
) -> ValidationResult:
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

    def evaluate(self, context) -> list[ValidationResult]:
        missing = [asset.name for asset in context.assets if asset.location is None]
        return [
            _finding(
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

    def evaluate(self, context) -> list[ValidationResult]:
        unclassified = [
            asset.name for asset in context.assets if asset.asset_type == "other"
        ]
        return [
            _finding(
                self.rule_id,
                unclassified,
                len(context.assets),
                Severity.WARNING,
                "Assets have an unclassified asset type",
                "All assets classified",
            )
        ]


class DuplicateAssetNameRule:
    """Asset names are unique within a project (SDS-005 §4)."""

    rule_id = "agl.asset.duplicate-names"
    description = "Asset names are unique"

    def evaluate(self, context) -> list[ValidationResult]:
        counts = Counter(asset.name for asset in context.assets)
        duplicates = [
            f"{name} (x{count})" for name, count in counts.items() if count > 1
        ]
        return [
            _finding(
                self.rule_id,
                duplicates,
                len(context.assets),
                Severity.ERROR,
                "Duplicate asset names found",
                "All asset names unique",
            )
        ]


class SkippedEntitiesRule:
    """Drawings interpreted without skipped entities (SDS-005 §4)."""

    rule_id = "agl.drawing.skipped-entities"
    description = "No entities were skipped during interpretation"

    def evaluate(self, context) -> list[ValidationResult]:
        skipped = [
            f"{snapshot.metadata.get('source_path', snapshot.snapshot_id)} "
            f"({snapshot.metadata['skipped_entities']} skipped)"
            for snapshot in context.snapshots
            if snapshot.metadata.get("skipped_entities", "0") not in ("", "0")
        ]
        return [
            _finding(
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

    def evaluate(self, context) -> list[ValidationResult]:
        empty = [
            f"{snapshot.metadata.get('source_path', snapshot.snapshot_id)}:"
            f"{layer.name}"
            for snapshot in context.snapshots
            for layer in snapshot.layers
            if layer.entity_count == 0
        ]
        total_layers = sum(len(snapshot.layers) for snapshot in context.snapshots)
        return [
            _finding(
                self.rule_id,
                empty,
                total_layers,
                Severity.INFO,
                "Defined layers carry no entities",
                "All defined layers carry entities",
            )
        ]


def standard_rules() -> list:
    """The SDS-005 standard rule pack, in evaluation order."""
    return [
        AssetLocationRule(),
        AssetClassificationRule(),
        DuplicateAssetNameRule(),
        SkippedEntitiesRule(),
        EmptyLayersRule(),
    ]
