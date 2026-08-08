"""Plugin contracts and controlled runtime (SDS-002 §10).

Plugins depend only on the public contracts in this module. The runtime
validates manifests, checks version compatibility, isolates activation
failures, and keeps every registered extension traceable to its plugin
identity and version (SDS-002 §10.3, §10.5).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum

from aet.core.config import PLUGIN_API_VERSION, AppConfig
from aet.core.errors import InfrastructureError
from aet.core.logging import StructuredLogger, get_logger
from aet.core.outcome import Outcome


class PluginCategory(StrEnum):
    """Planned plugin categories (SDS-002 §10.2)."""

    IMPORTER = "importer"
    DRAWING_INTERPRETER = "drawing-interpreter"
    ASSET_EXTRACTOR = "asset-extractor"
    VALIDATION_RULE = "validation-rule"
    REPORT_PROVIDER = "report-provider"
    EXPORTER = "exporter"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """Identity, version, and compatibility declaration for a plugin."""

    plugin_id: str
    name: str
    version: str
    category: PluginCategory
    api_version: str = PLUGIN_API_VERSION
    description: str = ""


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Approved contract through which configuration reaches plugins."""

    config: AppConfig
    logger: StructuredLogger


@dataclass(frozen=True, slots=True)
class RegisteredExtension:
    """An activated extension, traceable to its providing plugin."""

    manifest: PluginManifest
    extension: object


class Plugin(abc.ABC):
    """Base contract every plugin implements."""

    @property
    @abc.abstractmethod
    def manifest(self) -> PluginManifest:
        """Manifest describing this plugin."""

    @abc.abstractmethod
    def activate(self, context: PluginContext) -> object:
        """Build and return the extension object to register."""

    def deactivate(self) -> None:  # noqa: B027 - opt-in hook, not a requirement
        """Release plugin resources. Optional lifecycle hook.

        Deliberately concrete and empty: a plugin holding no resources should
        not be forced to implement it, so this is not abstract.
        """


@dataclass(slots=True)
class PluginRuntime:
    """Controlled plugin loading and registration (SDS-002 §10.3)."""

    config: AppConfig = field(default_factory=AppConfig)
    logger: StructuredLogger = field(
        default_factory=lambda: get_logger("plugin-runtime")
    )
    _extensions: dict[PluginCategory, list[RegisteredExtension]] = field(
        default_factory=dict
    )
    _quarantined: dict[str, str] = field(default_factory=dict)

    def register(self, plugin: Plugin) -> Outcome[PluginManifest]:
        """Validate, activate, and register a plugin.

        Activation failures are isolated: the plugin is quarantined and a
        failed outcome is returned without destabilising the runtime.
        """
        manifest = plugin.manifest
        if not manifest.plugin_id or not manifest.version:
            return Outcome.fail(
                InfrastructureError.code,
                "Plugin manifest is missing a plugin_id or version",
                remediation="Declare plugin_id and version in the manifest.",
            )
        if not self._compatible(manifest.api_version):
            self.logger.warn(
                "Rejected incompatible plugin",
                plugin_id=manifest.plugin_id,
                plugin_version=manifest.version,
            )
            return Outcome.fail(
                InfrastructureError.code,
                f"Plugin '{manifest.plugin_id}' declares incompatible API "
                f"version {manifest.api_version}; runtime provides "
                f"{self.config.plugin_api_version}",
                remediation="Update the plugin to the supported API version.",
            )
        try:
            extension = plugin.activate(
                PluginContext(config=self.config, logger=self.logger)
            )
        except Exception as exc:  # noqa: BLE001 - isolate plugin failures
            self._quarantined[manifest.plugin_id] = str(exc)
            self.logger.error(
                "Plugin activation failed; plugin quarantined",
                plugin_id=manifest.plugin_id,
                plugin_version=manifest.version,
                error_code=InfrastructureError.code,
            )
            return Outcome.fail(
                InfrastructureError.code,
                f"Plugin '{manifest.plugin_id}' failed to activate: {exc}",
            )
        registered = RegisteredExtension(manifest=manifest, extension=extension)
        self._extensions.setdefault(manifest.category, []).append(registered)
        self.logger.audit(
            "Plugin registered",
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.version,
            operation="register-plugin",
        )
        return Outcome.ok(manifest)

    def extensions(self, category: PluginCategory) -> list[RegisteredExtension]:
        """Return activated extensions registered for a category."""
        return list(self._extensions.get(category, []))

    @property
    def quarantined(self) -> dict[str, str]:
        """Plugin IDs quarantined by activation failure, with reasons."""
        return dict(self._quarantined)

    def _compatible(self, api_version: str) -> bool:
        provided = self.config.plugin_api_version.split(".")[0]
        return api_version.split(".")[0] == provided
