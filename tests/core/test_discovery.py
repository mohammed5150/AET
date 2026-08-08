"""Tests for SDS-014: plugin discovery."""

import sys
from pathlib import Path

from aet.core.config import AppConfig
from aet.core.discovery import DiscoveryReport, discover_plugins
from aet.core.plugins import PluginCategory, PluginRuntime
from aet.services.use_cases import ApplicationService

_WORKING_PLUGIN = """
from aet.core.plugins import Plugin, PluginCategory, PluginManifest


class RulePackPlugin(Plugin):
    @property
    def manifest(self):
        return PluginManifest(
            plugin_id="vendor.rule-pack",
            name="Rule Pack",
            version="1.0.0",
            category=PluginCategory.VALIDATION_RULE,
        )

    def activate(self, context):
        return {"kind": "rule-pack"}
"""

_BROKEN_ON_IMPORT = """
raise RuntimeError("this plugin explodes while importing")
"""

_NO_PLUGIN = """
VALUE = 1
"""

_BROKEN_CONSTRUCTOR = """
from aet.core.plugins import Plugin, PluginCategory, PluginManifest


class ExplodingPlugin(Plugin):
    def __init__(self):
        raise RuntimeError("cannot be built")

    @property
    def manifest(self):
        return PluginManifest(
            plugin_id="vendor.exploding", name="X", version="1.0.0",
            category=PluginCategory.VALIDATION_RULE,
        )

    def activate(self, context):
        return object()
"""

_INCOMPATIBLE = """
from aet.core.plugins import Plugin, PluginCategory, PluginManifest


class FuturePlugin(Plugin):
    @property
    def manifest(self):
        return PluginManifest(
            plugin_id="vendor.future",
            name="Future",
            version="1.0.0",
            category=PluginCategory.VALIDATION_RULE,
            api_version="99.0",
        )

    def activate(self, context):
        return object()
"""


def _runtime(*directories: Path) -> PluginRuntime:
    return PluginRuntime(config=AppConfig(plugin_dirs=tuple(directories)))


def _write(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _discover(runtime: PluginRuntime) -> DiscoveryReport:
    # Entry points are excluded so the environment's installed distributions
    # cannot make these assertions depend on what else is installed.
    return discover_plugins(runtime, include_entry_points=False)


# -- §7.1 a configured directory yields registered plugins -----------------


def test_a_plugin_on_disk_is_loaded_and_registered(tmp_path: Path):
    _write(tmp_path / "plugins", "rule_pack.py", _WORKING_PLUGIN)
    runtime = _runtime(tmp_path / "plugins")
    report = _discover(runtime)

    assert report.registered_ids == ["vendor.rule-pack"]
    assert report.rejected == {}
    [registered] = runtime.extensions(PluginCategory.VALIDATION_RULE)
    assert registered.manifest.plugin_id == "vendor.rule-pack"
    assert registered.extension == {"kind": "rule-pack"}


def test_a_package_directory_is_loaded_too(tmp_path: Path):
    package = tmp_path / "plugins" / "vendor_pack"
    _write(package, "__init__.py", _WORKING_PLUGIN)
    assert _discover(_runtime(tmp_path / "plugins")).registered_ids == [
        "vendor.rule-pack"
    ]


# -- §7.2 nothing is searched that was not configured ----------------------


def test_no_directories_configured_means_nothing_is_searched(tmp_path: Path):
    # Loading a plugin executes its code, so there is no default search path.
    _write(tmp_path / "plugins", "rule_pack.py", _WORKING_PLUGIN)
    report = _discover(PluginRuntime(config=AppConfig()))
    assert report.registered == []
    assert report.rejected == {}


def test_a_configured_directory_that_does_not_exist_is_reported(tmp_path: Path):
    # A mistyped path must not look like a directory holding no plugins.
    report = _discover(_runtime(tmp_path / "absent"))
    assert report.missing_directories == [str(tmp_path / "absent")]
    assert report.registered == []


def test_underscored_names_are_skipped(tmp_path: Path):
    directory = tmp_path / "plugins"
    _write(directory, "_helper.py", _WORKING_PLUGIN)
    _write(directory / "__pycache__", "stale.py", _WORKING_PLUGIN)
    assert _discover(_runtime(directory)).registered == []


def test_non_python_files_are_ignored(tmp_path: Path):
    directory = tmp_path / "plugins"
    _write(directory, "notes.txt", "not python")
    _write(directory, "rule_pack.py", _WORKING_PLUGIN)
    assert _discover(_runtime(directory)).registered_ids == ["vendor.rule-pack"]


# -- §7.3 one broken plugin does not stop the others -----------------------


def test_a_module_failing_to_import_is_recorded_and_skipped(tmp_path: Path):
    directory = tmp_path / "plugins"
    _write(directory, "aaa_broken.py", _BROKEN_ON_IMPORT)
    _write(directory, "zzz_working.py", _WORKING_PLUGIN)

    report = _discover(_runtime(directory))
    # The broken module sorts first, so a working plugin after it proves the
    # failure did not abort discovery.
    assert report.registered_ids == ["vendor.rule-pack"]
    [(source, reason)] = report.rejected.items()
    assert "aaa_broken.py" in source
    assert "explodes while importing" in reason


def test_a_plugin_that_cannot_be_constructed_is_recorded(tmp_path: Path):
    directory = tmp_path / "plugins"
    _write(directory, "exploding.py", _BROKEN_CONSTRUCTOR)
    report = _discover(_runtime(directory))
    assert report.registered == []
    assert any("cannot be built" in reason for reason in report.rejected.values())


def test_a_module_defining_no_plugin_is_recorded(tmp_path: Path):
    _write(tmp_path / "plugins", "empty.py", _NO_PLUGIN)
    report = _discover(_runtime(tmp_path / "plugins"))
    assert report.registered == []
    assert any(
        "defines no Plugin subclass" in reason for reason in report.rejected.values()
    )


def test_an_incompatible_api_version_is_rejected_by_the_runtime(tmp_path: Path):
    # The runtime's existing compatibility check still applies to a plugin
    # that arrived by discovery rather than by hand.
    _write(tmp_path / "plugins", "future.py", _INCOMPATIBLE)
    report = _discover(_runtime(tmp_path / "plugins"))
    assert report.registered == []
    assert any("incompatible API" in reason for reason in report.rejected.values())


# -- §7.4 a module contributes only what it defines ------------------------


def test_a_package_may_split_its_plugin_across_submodules(tmp_path: Path):
    # The ordinary way to write a package: define in a submodule, re-export
    # from __init__. Relative imports only resolve because the package is
    # given search locations and entered into sys.modules (SDS-014 §5.1).
    package = tmp_path / "plugins" / "vendor_pack"
    _write(package, "rules.py", _WORKING_PLUGIN)
    _write(package, "__init__.py", "from .rules import RulePackPlugin\n")
    report = _discover(_runtime(tmp_path / "plugins"))
    assert report.registered_ids == ["vendor.rule-pack"]
    assert report.rejected == {}


def test_a_package_failing_to_import_leaves_nothing_in_sys_modules(tmp_path: Path):
    package = tmp_path / "plugins" / "broken_pack"
    _write(package, "__init__.py", _BROKEN_ON_IMPORT)
    report = _discover(_runtime(tmp_path / "plugins"))
    assert report.registered == []
    # A half-executed module must not be left for a later import to find.
    assert "aet_plugin_broken_pack" not in sys.modules


def test_a_class_imported_from_elsewhere_is_not_registered(tmp_path: Path):
    # Importing somebody else's plugin does not make it yours to register.
    directory = tmp_path / "plugins"
    _write(
        directory,
        "importer.py",
        "from aet.core.plugins import Plugin  # noqa: F401\n\nVALUE = 1\n",
    )
    report = _discover(_runtime(directory))
    assert report.registered == []
    assert any(
        "defines no Plugin subclass" in reason for reason in report.rejected.values()
    )


# -- §7.5 discovery reaches the application service ------------------------


def test_the_service_discovers_plugins_from_its_configuration(tmp_path: Path):
    _write(tmp_path / "plugins", "rule_pack.py", _WORKING_PLUGIN)
    service = ApplicationService(config=AppConfig(plugin_dirs=(tmp_path / "plugins",)))
    assert service.discovery.registered_ids == ["vendor.rule-pack"]


def test_the_service_discovers_nothing_without_configured_directories():
    service = ApplicationService(config=AppConfig())
    assert service.discovery.registered == []
    assert service.discovery.rejected == {}


def test_an_injected_runtime_is_left_alone(tmp_path: Path):
    # A caller supplying its own runtime has already decided what is loaded.
    _write(tmp_path / "plugins", "rule_pack.py", _WORKING_PLUGIN)
    runtime = PluginRuntime(config=AppConfig(plugin_dirs=(tmp_path / "plugins",)))
    service = ApplicationService(
        plugins=runtime, config=AppConfig(plugin_dirs=(tmp_path / "plugins",))
    )
    assert service.discovery.registered == []
    assert runtime.extensions(PluginCategory.VALIDATION_RULE) == []
