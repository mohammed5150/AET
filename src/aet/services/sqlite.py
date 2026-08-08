"""SQLite-backed repositories (SDS-013).

Everything the toolkit derived used to vanish at process exit, so each run
re-parsed its drawings and re-read its registry from scratch. These
repositories satisfy the same :class:`~aet.services.persistence.Repository`
protocol as the in-memory ones, so nothing above the persistence boundary
changes.

Rows keep their scope in indexed columns and the rest of the entity in a JSON
document. A fully normalized schema would buy SQL-level aggregation the
application does not yet perform, at the cost of nine hand-written schemas
that must track every model change; the indexed columns are the part that
carries its weight today, because project-scoped reads are the queries the
application actually makes (SDS-013 §5).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from aet.core.errors import InfrastructureError
from aet.models.asset import Asset, AssetRelation
from aet.models.drawing import DrawingSnapshot
from aet.models.project import Project, SourceInput
from aet.models.report import Report, ReportArtifact
from aet.models.validation import ValidationResult, ValidationRun
from aet.services.persistence import AuditTrail, Repositories
from aet.services.serialization import from_document, to_document


@contextmanager
def _wrapped_errors(action: str) -> Iterator[None]:
    """Turn sqlite failures into INFRASTRUCTURE_ERROR (SDS-002 §12.2)."""
    try:
        yield
    except sqlite3.Error as exc:
        raise InfrastructureError(
            f"Database failure trying to {action}: {exc}",
            remediation="Check the database file is writable and not corrupt.",
        ) from exc


#: Scope column stored alongside the document, per table. Indexed, because a
#: project-scoped read is the query the application makes on every use case.
_SCOPE_COLUMN = "project_id"


class SqliteRepository[T]:
    """One table of entities, keyed by a stable identifier."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        table: str,
        model: type[T],
        key: Callable[[T], str],
        scope: Callable[[T], str | None] | None = None,
    ) -> None:
        self._connection = connection
        self._table = table
        self._model = model
        self._key = key
        self._scope = scope
        self._create_table()

    def add(self, item: T) -> None:
        """Insert the entity, replacing any earlier row with the same id."""
        with _wrapped_errors(f"write to {self._table}"):
            self._connection.execute(
                f"INSERT OR REPLACE INTO {self._table} "  # noqa: S608 - fixed name
                "(id, project_id, document) VALUES (?, ?, ?)",
                (
                    self._key(item),
                    self._scope(item) if self._scope else None,
                    json.dumps(to_document(item)),
                ),
            )
            self._connection.commit()

    def get(self, item_id: str) -> T | None:
        with _wrapped_errors(f"read from {self._table}"):
            row = self._connection.execute(
                f"SELECT document FROM {self._table} WHERE id = ?",  # noqa: S608
                (item_id,),
            ).fetchone()
        return self._hydrate(row[0]) if row else None

    # Declared before `list`, which shadows the builtin inside the class body
    # and would leave this method's `list[T]` annotation unresolvable.
    def list_for_project(self, project_id: str) -> list[T]:
        """Entities scoped to one project, served by the index.

        The in-memory store answers this by scanning; here it is a lookup, so
        a project's assets are read without walking every other project's.
        """
        if self._scope is None:
            return [
                item
                for item in self.list()
                if getattr(item, _SCOPE_COLUMN, None) == project_id
            ]
        with _wrapped_errors(f"read from {self._table}"):
            rows = self._connection.execute(
                f"SELECT document FROM {self._table} "  # noqa: S608 - fixed name
                "WHERE project_id = ? ORDER BY rowid",
                (project_id,),
            ).fetchall()
        return [self._hydrate(row[0]) for row in rows]

    def list(self) -> list[T]:
        with _wrapped_errors(f"read from {self._table}"):
            rows = self._connection.execute(
                f"SELECT document FROM {self._table} ORDER BY rowid"  # noqa: S608
            ).fetchall()
        return [self._hydrate(row[0]) for row in rows]

    def _hydrate(self, document: str) -> T:
        return from_document(self._model, json.loads(document))

    def _create_table(self) -> None:
        with _wrapped_errors(f"create {self._table}"):
            self._connection.execute(
                f"CREATE TABLE IF NOT EXISTS {self._table} ("
                "id TEXT PRIMARY KEY, project_id TEXT, document TEXT NOT NULL)"
            )
            self._connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self._table}_project "
                f"ON {self._table} (project_id)"
            )
            self._connection.commit()


class SqliteAuditTrail:
    """Append-only audit records (SDS-002 §9.2.7)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        with _wrapped_errors("create audit_events"):
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS audit_events ("
                "rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT, document TEXT NOT NULL)"
            )
            self._connection.commit()

    def record(self, event: dict[str, str]) -> None:
        with _wrapped_errors("write to audit_events"):
            self._connection.execute(
                "INSERT INTO audit_events (document) VALUES (?)", (json.dumps(event),)
            )
            self._connection.commit()

    def events(self) -> list[dict[str, str]]:
        with _wrapped_errors("read from audit_events"):
            rows = self._connection.execute(
                "SELECT document FROM audit_events ORDER BY rowid_alias"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]


def connect(database: Path) -> sqlite3.Connection:
    """Open (creating if needed) the database, failing as infrastructure."""
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database)
    except (OSError, sqlite3.Error) as exc:
        raise InfrastructureError(
            f"Cannot open the database {database}: {exc}",
            remediation="Point --database at a writable path.",
        ) from exc
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def sqlite_repositories(connection: sqlite3.Connection) -> Repositories:
    """Build the SDS-002 §9.2 repositories against one connection."""
    return Repositories(
        projects=SqliteRepository(
            connection,
            "projects",
            Project,
            lambda item: item.project_id,
            lambda item: item.project_id,
        ),
        sources=SqliteRepository(
            connection,
            "source_inputs",
            SourceInput,
            lambda item: item.input_id,
            lambda item: item.project_id,
        ),
        snapshots=SqliteRepository(
            connection,
            "drawing_snapshots",
            DrawingSnapshot,
            lambda item: item.snapshot_id,
            lambda item: item.project_id,
        ),
        assets=SqliteRepository(
            connection,
            "assets",
            Asset,
            lambda item: item.asset_id,
            lambda item: item.project_id,
        ),
        # A relation carries no project of its own; it belongs to one through
        # the assets it links (SDS-011 §5.1), so it has no scope column.
        relations=SqliteRepository(
            connection,
            "asset_relations",
            AssetRelation,
            lambda item: item.relation_id,
        ),
        validation_runs=SqliteRepository(
            connection,
            "validation_runs",
            ValidationRun,
            lambda item: item.run_id,
            lambda item: item.project_id,
        ),
        validation_results=SqliteRepository(
            connection,
            "validation_results",
            ValidationResult,
            lambda item: item.result_id,
        ),
        reports=SqliteRepository(
            connection,
            "reports",
            Report,
            lambda item: item.report_id,
            lambda item: item.project_id,
        ),
        report_artifacts=SqliteRepository(
            connection,
            "report_artifacts",
            ReportArtifact,
            lambda item: item.artifact_id,
        ),
        audit=SqliteAuditTrail(connection),
    )


def audit_trail_of(repositories: Repositories) -> AuditTrail:
    """The audit trail behind a repository bundle."""
    return repositories.audit


def all_tables(connection: sqlite3.Connection) -> Iterable[str]:
    """Table names present, for diagnostics and tests."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]
