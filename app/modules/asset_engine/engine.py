"""Asset derivation from normalized drawings (SDS-002 §8.6).

Specialized derivation logic lives behind the :class:`AssetExtractor`
contract, which is also the extension point for asset-extractor plugins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.errors import AETError, ProcessingError
from app.core.logging import StructuredLogger, get_logger
from app.core.outcome import Outcome
from app.models.asset import Asset, AssetRelation
from app.models.drawing import DrawingSnapshot

STAGE_NAME = "asset-derivation"


@dataclass(frozen=True, slots=True)
class AssetCollection:
    """Structured asset output for downstream validation and reporting."""

    assets: list[Asset] = field(default_factory=list)
    relations: list[AssetRelation] = field(default_factory=list)


class AssetExtractor(Protocol):
    """Contract for asset derivation strategies."""

    def extract(self, snapshot: DrawingSnapshot) -> AssetCollection:
        """Derive engineering assets from a normalized snapshot."""
        ...


class NullAssetExtractor:
    """Placeholder extractor until domain derivation rules are specified."""

    def extract(self, snapshot: DrawingSnapshot) -> AssetCollection:
        return AssetCollection()


class AssetEngine:
    """Converts normalized drawing content into engineering assets."""

    stage = STAGE_NAME

    def __init__(
        self,
        extractor: AssetExtractor | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._extractor = extractor or NullAssetExtractor()
        self._logger = logger or get_logger("asset-engine")

    def derive(
        self,
        snapshot: DrawingSnapshot,
        *,
        correlation_id: str | None = None,
    ) -> Outcome[AssetCollection]:
        """Derive assets and relationships from one normalized snapshot."""
        try:
            collection = self._extractor.extract(snapshot)
        except AETError as error:
            self._log_failure(error.code, str(error), snapshot, correlation_id)
            return Outcome.from_error(error, correlation_id=correlation_id)
        except Exception as exc:  # noqa: BLE001 - wrap extractor failures
            message = (
                f"Asset derivation failed for snapshot "
                f"{snapshot.snapshot_id}: {exc}"
            )
            self._log_failure(ProcessingError.code, message, snapshot, correlation_id)
            return Outcome.fail(
                ProcessingError.code, message, correlation_id=correlation_id
            )
        self._logger.info(
            f"Derived {len(collection.assets)} asset(s)",
            stage=self.stage,
            project_id=snapshot.project_id,
            correlation_id=correlation_id,
        )
        return Outcome.ok(collection, correlation_id=correlation_id)

    def _log_failure(
        self,
        error_code: str,
        message: str,
        snapshot: DrawingSnapshot,
        correlation_id: str | None,
    ) -> None:
        self._logger.error(
            message,
            stage=self.stage,
            project_id=snapshot.project_id,
            correlation_id=correlation_id,
            error_code=error_code,
        )
