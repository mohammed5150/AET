"""DWG ingestion module (SDS-002 §8.4)."""

from app.modules.ingestion.engine import (
    FileSystemSourceReader,
    IngestionEngine,
    SourceFileInfo,
    SourceReader,
)

__all__ = [
    "FileSystemSourceReader",
    "IngestionEngine",
    "SourceFileInfo",
    "SourceReader",
]
