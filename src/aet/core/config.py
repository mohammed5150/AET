"""Application configuration resolution (SDS-002 §6.1).

Configuration failures are infrastructure errors (SDS-002 §12.2) and are
raised eagerly so the application fails early on invalid settings.

Settings resolve in layers, each overriding the one before it: dataclass
defaults, then ``AET_*`` environment variables via :meth:`AppConfig.from_env`,
then explicit overrides via :meth:`AppConfig.with_overrides` (used for CLI
flags).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path

PLUGIN_API_VERSION = "1.0"

ENV_PREFIX = "AET_"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Resolved application configuration."""

    data_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    #: SQLite file backing the repositories. ``None`` keeps everything in
    #: memory, so a run derives nothing it can hand to the next one.
    database: Path | None = None
    plugin_dirs: tuple[Path, ...] = ()
    log_level: str = "INFO"
    plugin_api_version: str = PLUGIN_API_VERSION

    def __post_init__(self) -> None:
        """Reject an unusable log level before the application starts."""
        from aet.core.logging import resolve_level

        resolve_level(self.log_level)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> AppConfig:
        """Build a configuration from a mapping, rejecting unknown keys."""
        from aet.core.errors import InfrastructureError

        known = {f.name for f in fields(cls)}
        unknown = sorted(set(mapping) - known)
        if unknown:
            raise InfrastructureError(
                f"Unknown configuration keys: {', '.join(unknown)}",
                remediation=f"Supported keys are: {', '.join(sorted(known))}",
            )
        return cls(**mapping)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppConfig:
        """Build a configuration from ``AET_*`` environment variables.

        Unset variables fall back to the dataclass defaults. ``AET_PLUGIN_DIRS``
        holds an ``os.pathsep``-separated list of directories.
        """
        env = os.environ if environ is None else environ
        values: dict[str, object] = {}
        if raw := env.get(f"{ENV_PREFIX}DATA_DIR"):
            values["data_dir"] = Path(raw)
        if raw := env.get(f"{ENV_PREFIX}LOG_DIR"):
            values["log_dir"] = Path(raw)
        if raw := env.get(f"{ENV_PREFIX}DATABASE"):
            values["database"] = Path(raw)
        if raw := env.get(f"{ENV_PREFIX}LOG_LEVEL"):
            values["log_level"] = raw.strip().upper()
        if raw := env.get(f"{ENV_PREFIX}PLUGIN_DIRS"):
            values["plugin_dirs"] = tuple(
                Path(part) for part in raw.split(os.pathsep) if part
            )
        return cls.from_mapping(values)

    def with_overrides(self, **overrides: object) -> AppConfig:
        """Return a copy with the non-``None`` overrides applied.

        ``None`` means "not supplied", so unset CLI flags leave the value
        resolved by the layer beneath them untouched.
        """
        supplied = {key: value for key, value in overrides.items() if value is not None}
        if not supplied:
            return self
        known = {f.name for f in fields(self)}
        unknown = sorted(set(supplied) - known)
        if unknown:
            from aet.core.errors import InfrastructureError

            raise InfrastructureError(
                f"Unknown configuration keys: {', '.join(unknown)}",
                remediation=f"Supported keys are: {', '.join(sorted(known))}",
            )
        return replace(self, **supplied)  # type: ignore[arg-type]
