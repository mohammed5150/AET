"""Plugin discovery from disk and entry points (SDS-014).

The plugin runtime could validate, activate, quarantine and version-check a
plugin, but nothing could give it one: `register` took an already-constructed
object, so the whole extension mechanism was unreachable by a third party.

Discovery is **never implicit**. Loading a plugin executes its module, so a
directory is searched only when an operator has named it in
``plugin_dirs``/``AET_PLUGIN_DIRS``. There is no default search path, no
scan of the working directory, and no attempt to be helpful about
directories nobody configured (SDS-014 §4).
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard

from aet.core.errors import InfrastructureError
from aet.core.plugins import Plugin, PluginManifest, PluginRuntime

if TYPE_CHECKING:
    from types import ModuleType

#: Entry-point group an installed distribution declares plugins under.
ENTRY_POINT_GROUP = "aet.plugins"


@dataclass(frozen=True, slots=True)
class DiscoveryReport:
    """What discovery found, and what it refused (SDS-014 §6)."""

    registered: list[PluginManifest] = field(default_factory=list)
    #: Source identity mapped to why it did not yield a registered plugin.
    rejected: dict[str, str] = field(default_factory=dict)
    #: Directories named in configuration that do not exist.
    missing_directories: list[str] = field(default_factory=list)

    @property
    def registered_ids(self) -> list[str]:
        return [manifest.plugin_id for manifest in self.registered]


def discover_plugins(
    runtime: PluginRuntime,
    *,
    include_entry_points: bool = True,
) -> DiscoveryReport:
    """Load and register plugins from the runtime's configured sources."""
    registered: list[PluginManifest] = []
    rejected: dict[str, str] = {}
    missing: list[str] = []

    for directory in runtime.config.plugin_dirs:
        if not directory.is_dir():
            # Named but absent: reported rather than ignored, because a
            # mistyped path would otherwise look like a directory holding no
            # plugins (SDS-014 §6.1).
            missing.append(str(directory))
            continue
        for path in _candidate_paths(directory):
            _load_source(
                runtime,
                str(path),
                partial(_module_from_path, path),
                registered,
                rejected,
            )

    if include_entry_points:
        for entry_point in _entry_points():
            _load_source(
                runtime,
                f"{ENTRY_POINT_GROUP}:{entry_point.name}",
                entry_point.load,
                registered,
                rejected,
            )

    runtime.logger.info(
        f"Plugin discovery registered {len(registered)} plugin(s), "
        f"rejected {len(rejected)}",
        operation="discover-plugins",
    )
    return DiscoveryReport(
        registered=registered, rejected=rejected, missing_directories=missing
    )


def _candidate_paths(directory: Path) -> list[Path]:
    """Modules and packages a plugin directory offers, in a stable order.

    Names beginning with ``_`` are skipped, so a directory can keep helpers
    and ``__pycache__`` beside its plugins.
    """
    candidates = [
        path
        for path in directory.iterdir()
        if not path.name.startswith("_")
        and (
            (path.is_file() and path.suffix == ".py")
            or (path.is_dir() and (path / "__init__.py").is_file())
        )
    ]
    return sorted(candidates)


def _load_source(
    runtime: PluginRuntime,
    identity: str,
    load: Callable[[], object],
    registered: list[PluginManifest],
    rejected: dict[str, str],
) -> None:
    """Load one source and register every plugin it defines.

    A source that raises is recorded and skipped: one broken plugin must not
    stop the others loading, which is the same isolation SDS-002 §10.5
    requires of activation.
    """
    try:
        loaded = load()
    except Exception as exc:  # noqa: BLE001 - isolate third-party import failures
        rejected[identity] = f"failed to load: {exc}"
        runtime.logger.error(
            f"Plugin source '{identity}' failed to load: {exc}",
            operation="discover-plugins",
            error_code=InfrastructureError.code,
        )
        return

    plugin_types = _plugin_types(loaded)
    if not plugin_types:
        rejected[identity] = "defines no Plugin subclass"
        return

    for plugin_type in plugin_types:
        try:
            plugin = plugin_type()
        except Exception as exc:  # noqa: BLE001 - isolate third-party constructors
            rejected[f"{identity}:{plugin_type.__name__}"] = f"failed to build: {exc}"
            continue
        outcome = runtime.register(plugin)
        if outcome.success and outcome.payload is not None:
            registered.append(outcome.payload)
        else:
            rejected[f"{identity}:{plugin_type.__name__}"] = outcome.message


def _plugin_types(loaded: object) -> list[type[Plugin]]:
    """Concrete Plugin subclasses a loaded source offers.

    A module contributes the plugins it defines itself, so importing `Plugin`
    or another plugin does not register somebody else's twice. An entry point
    may instead resolve directly to a plugin class.
    """
    if inspect.isclass(loaded) and _is_concrete_plugin(loaded):
        return [loaded]
    if not inspect.ismodule(loaded):
        return []
    module: ModuleType = loaded
    return [
        member
        for _, member in inspect.getmembers(module, inspect.isclass)
        if _is_concrete_plugin(member) and _belongs_to(member, module.__name__)
    ]


def _belongs_to(candidate: type, module_name: str) -> bool:
    """Whether a class was defined by this source rather than imported.

    A package's own submodules count, so the usual layout — define in
    ``rules.py``, re-export from ``__init__`` — registers the plugin, while a
    class imported from somebody else's module still does not.
    """
    origin = candidate.__module__
    return origin == module_name or origin.startswith(f"{module_name}.")


def _is_concrete_plugin(candidate: type) -> TypeGuard[type[Plugin]]:
    return (
        issubclass(candidate, Plugin)
        and candidate is not Plugin
        and not inspect.isabstract(candidate)
    )


def _module_from_path(path: Path) -> ModuleType:
    """Import one file or package by path, under a namespaced module name.

    A package is given its own search locations and entered into
    ``sys.modules`` before execution, so a plugin split across submodules can
    use relative imports — the ordinary way to write one. Without both, a
    package whose ``__init__`` says ``from .rules import ...`` fails to load
    at all (SDS-014 §5.1).
    """
    is_package = path.is_dir()
    target = path / "__init__.py" if is_package else path
    module_name = f"aet_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        target,
        submodule_search_locations=[str(path)] if is_package else None,
    )
    if spec is None or spec.loader is None:
        raise InfrastructureError(f"Cannot import a plugin from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Leave no half-executed module behind for a later import to find.
        sys.modules.pop(module_name, None)
        raise
    return module


def _entry_points() -> list[metadata.EntryPoint]:
    return list(metadata.entry_points(group=ENTRY_POINT_GROUP))
