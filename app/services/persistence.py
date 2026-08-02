"""Repository abstractions and in-memory implementations (SDS-002 §8.9, §9).

Application services depend on the :class:`Repository` protocol, never on a
concrete storage engine, so the in-memory stores used today can be replaced
by a relational database without breaking application contracts
(SDS-002 §9.5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.models.asset import Asset, AssetRelation
from app.models.drawing import DrawingSnapshot
from app.models.project import Project, SourceInput
from app.models.report import Report, ReportArtifact
from app.models.validation import ValidationResult, ValidationRun


class Repository[T](Protocol):
    """Minimal repository contract exposed to application services."""

    def add(self, item: T) -> None: ...

    def get(self, item_id: str) -> T | None: ...

    def list(self) -> list[T]: ...


class InMemoryRepository[T]:
    """Dictionary-backed repository keyed by a stable entity identifier."""

    def __init__(self, key: Callable[[T], str]) -> None:
        self._key = key
        self._items: dict[str, T] = {}

    def add(self, item: T) -> None:
        self._items[self._key(item)] = item

    def get(self, item_id: str) -> T | None:
        return self._items.get(item_id)

    def list(self) -> list[T]:
        return list(self._items.values())


@dataclass(frozen=True, slots=True)
class Repositories:
    """Bundle of repositories covering the SDS-002 §9.2 data domains."""

    projects: InMemoryRepository[Project]
    sources: InMemoryRepository[SourceInput]
    snapshots: InMemoryRepository[DrawingSnapshot]
    assets: InMemoryRepository[Asset]
    relations: InMemoryRepository[AssetRelation]
    validation_runs: InMemoryRepository[ValidationRun]
    validation_results: InMemoryRepository[ValidationResult]
    reports: InMemoryRepository[Report]
    report_artifacts: InMemoryRepository[ReportArtifact]
    audit_events: list[dict[str, str]] = field(default_factory=list)

    def record_audit_event(self, event: dict[str, str]) -> None:
        """Append an audit record (SDS-002 §9.2.7)."""
        self.audit_events.append(dict(event))


def in_memory_repositories() -> Repositories:
    """Build a fresh set of in-memory repositories."""
    return Repositories(
        projects=InMemoryRepository(lambda item: item.project_id),
        sources=InMemoryRepository(lambda item: item.input_id),
        snapshots=InMemoryRepository(lambda item: item.snapshot_id),
        assets=InMemoryRepository(lambda item: item.asset_id),
        relations=InMemoryRepository(lambda item: item.relation_id),
        validation_runs=InMemoryRepository(lambda item: item.run_id),
        validation_results=InMemoryRepository(lambda item: item.result_id),
        reports=InMemoryRepository(lambda item: item.report_id),
        report_artifacts=InMemoryRepository(lambda item: item.artifact_id),
    )
