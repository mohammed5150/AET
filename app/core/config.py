"""Application configuration resolution (SDS-002 §6.1).

Configuration failures are infrastructure errors (SDS-002 §12.2) and are
raised eagerly so the application fails early on invalid settings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path

PLUGIN_API_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Resolved application configuration."""

    data_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    plugin_dirs: tuple[Path, ...] = ()
    log_level: str = "INFO"
    plugin_api_version: str = PLUGIN_API_VERSION

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> AppConfig:
        """Build a configuration from a mapping, rejecting unknown keys."""
        from app.core.errors import InfrastructureError

        known = {f.name for f in fields(cls)}
        unknown = sorted(set(mapping) - known)
        if unknown:
            raise InfrastructureError(
                f"Unknown configuration keys: {', '.join(unknown)}",
                remediation=f"Supported keys are: {', '.join(sorted(known))}",
            )
        return cls(**mapping)  # type: ignore[arg-type]
