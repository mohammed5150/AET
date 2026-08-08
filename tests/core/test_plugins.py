"""Tests for the plugin runtime (SDS-002 §10)."""

from typing import Any

from aet.core.plugins import (
    Plugin,
    PluginCategory,
    PluginManifest,
    PluginRuntime,
)


class _StubPlugin(Plugin):
    def __init__(self, manifest: PluginManifest, extension: object = None):
        self._manifest = manifest
        self._extension = extension or object()

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    def activate(self, context) -> object:
        return self._extension


class _ExplodingPlugin(_StubPlugin):
    def activate(self, context) -> object:
        raise RuntimeError("activation exploded")


def _manifest(**overrides) -> PluginManifest:
    values: dict[str, Any] = {
        "plugin_id": "vendor.rule-pack",
        "name": "Rule Pack",
        "version": "1.0.0",
        "category": PluginCategory.VALIDATION_RULE,
    }
    values.update(overrides)
    return PluginManifest(**values)


def test_register_compatible_plugin_exposes_traceable_extension():
    runtime = PluginRuntime()
    extension = object()
    outcome = runtime.register(_StubPlugin(_manifest(), extension))
    assert outcome.success
    registered = runtime.extensions(PluginCategory.VALIDATION_RULE)
    assert len(registered) == 1
    assert registered[0].extension is extension
    assert registered[0].manifest.plugin_id == "vendor.rule-pack"
    assert registered[0].manifest.version == "1.0.0"


def test_incompatible_api_version_is_rejected():
    runtime = PluginRuntime()
    outcome = runtime.register(_StubPlugin(_manifest(api_version="2.0")))
    assert not outcome.success
    assert outcome.error_code == "INFRASTRUCTURE_ERROR"
    assert runtime.extensions(PluginCategory.VALIDATION_RULE) == []


def test_activation_failure_is_isolated_and_quarantined():
    runtime = PluginRuntime()
    outcome = runtime.register(_ExplodingPlugin(_manifest()))
    assert not outcome.success
    assert "activation exploded" in outcome.message
    assert "vendor.rule-pack" in runtime.quarantined
    healthy = _StubPlugin(_manifest(plugin_id="vendor.other"))
    assert runtime.register(healthy).success


def test_manifest_missing_identity_is_rejected():
    runtime = PluginRuntime()
    outcome = runtime.register(_StubPlugin(_manifest(plugin_id="")))
    assert not outcome.success
    assert runtime.extensions(PluginCategory.VALIDATION_RULE) == []
