"""Repository abstractions and in-memory implementations (SDS-002 §8.9, §9).

Application services depend on the :class:`Repository` protocol, never on a
concrete storage engine, so the in-memory stores used today can be replaced
by a relational database without breaking application contracts
(SDS-002 §9.5).

:class:`RepositoryAuditSink` is the audit store of SDS-002 §11.4: it is the
sink that turns emitted audit events into the audit-and-logs data domain of
§9.2.7, so the two stay in step without every call site writing twice.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.core.logging import AUDIT_LOGGER_NAME
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


class RepositoryAuditSink(logging.Handler):
    """Routes emitted audit events into the audit store (SDS-002 §9.2.7).

    Attached to the audit logger, so an event recorded once through the
    logging API reaches both the audit log file and the audit data domain.
    """

    def __init__(self, repositories: Repositories) -> None:
        super().__init__(level=logging.INFO)
        self._repositories = repositories

    def emit(self, record: logging.LogRecord) -> None:
        """Append one structured audit event; ignore anything unparsable."""
        try:
            event = json.loads(record.getMessage())
        except (TypeError, ValueError):
            return
        if not isinstance(event, dict):
            return
        self._repositories.record_audit_event(
            {str(key): str(value) for key, value in event.items() if value is not None}
        )


def attach_audit_sink(repositories: Repositories) -> RepositoryAuditSink:
    """Install the audit store sink, replacing any previously attached one.

    Raises the audit logger to INFO so audit events are not filtered out
    before reaching the store when logging is otherwise unconfigured.
    """
    detach_audit_sink()
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    sink = RepositoryAuditSink(repositories)
    logger.addHandler(sink)
    return sink


def detach_audit_sink() -> None:
    """Remove any audit store sink previously attached to the audit logger."""
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    for handler in [
        handler
        for handler in logger.handlers
        if isinstance(handler, RepositoryAuditSink)
    ]:
        logger.removeHandler(handler)
        handler.close()


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
