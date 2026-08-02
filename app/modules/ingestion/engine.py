"""Source file discovery, registration, and metadata reading (SDS-002 §8.4).

External DWG tooling is adapted behind the :class:`SourceReader` interface so
downstream modules only ever see standardized ingestion output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.errors import AETError, InputError
from app.core.logging import StructuredLogger, get_logger
from app.core.outcome import Outcome
from app.models.project import Project, SourceInput
from app.utils.hashing import sha256_file

STAGE_NAME = "ingestion"


@dataclass(frozen=True, slots=True)
class SourceFileInfo:
    """Standardized source metadata emitted by readers."""

    path: str
    size_bytes: int
    file_hash: str


class SourceReader(Protocol):
    """Adapter interface hiding external file/DWG tooling."""

    def probe(self, path: Path) -> SourceFileInfo:
        """Read source metadata, raising :class:`InputError` on bad input."""
        ...


class FileSystemSourceReader:
    """Default reader backed by the local filesystem."""

    def probe(self, path: Path) -> SourceFileInfo:
        if not path.is_file():
            raise InputError(
                f"Source file not found: {path}",
                remediation="Check the file path and register the file again.",
            )
        return SourceFileInfo(
            path=str(path),
            size_bytes=path.stat().st_size,
            file_hash=sha256_file(path),
        )


class IngestionEngine:
    """Registers project inputs and emits standardized ingestion output."""

    stage = STAGE_NAME

    def __init__(
        self,
        reader: SourceReader | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._reader = reader or FileSystemSourceReader()
        self._logger = logger or get_logger(STAGE_NAME)

    def register_input(
        self,
        project: Project,
        path: Path,
        *,
        correlation_id: str | None = None,
    ) -> Outcome[SourceInput]:
        """Register one source file as a project input."""
        try:
            info = self._reader.probe(path)
        except AETError as error:
            self._logger.error(
                str(error),
                stage=self.stage,
                project_id=project.project_id,
                correlation_id=correlation_id,
                error_code=error.code,
            )
            return Outcome.from_error(error, correlation_id=correlation_id)
        source = SourceInput(
            project_id=project.project_id,
            path=info.path,
            file_hash=info.file_hash,
            provenance=f"filesystem:{info.path}",
        )
        self._logger.audit(
            "Source input registered",
            stage=self.stage,
            operation="register-input",
            project_id=project.project_id,
            correlation_id=correlation_id,
        )
        return Outcome.ok(source, correlation_id=correlation_id)
