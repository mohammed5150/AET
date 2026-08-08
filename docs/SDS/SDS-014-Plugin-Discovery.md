# SDS-014 – Plugin Discovery

## 1. Purpose

This document specifies how plugins reach the plugin runtime.

SDS-002 §10 designed a full extension mechanism — manifests, categories, API
version compatibility, isolated activation, quarantine — and the runtime
implements all of it. But `register` takes an already-constructed plugin
object, and nothing constructed one. The mechanism was complete and
unreachable: no third party could contribute a plugin without editing the
application.

## 2. Scope

SDS-014 covers:

- Loading plugins from operator-configured directories
- Loading plugins declared by installed distributions
- Reporting what was loaded, what was refused, and why
- Wiring discovery into the application service

SDS-014 does **not** cover:

- Sandboxing or restricting what a plugin may do (§4.1)
- Dependency resolution between plugins
- Unloading or reloading a plugin at runtime

## 3. Sources

**Directories.** Every `.py` file and every package directory in a configured
`plugin_dirs` entry, excluding names beginning with `_` so a directory can
hold helpers and `__pycache__` beside its plugins. Candidates load in sorted
order, so a report reads the same way twice.

**Entry points.** Distributions declaring the `aet.plugins` group, the
standard mechanism for an installed package to advertise an extension. An
entry point may resolve to a module or directly to a plugin class.

## 4. Discovery Is Never Implicit

Loading a plugin **executes its module**. Discovery therefore searches only
directories an operator has named in `plugin_dirs` / `AET_PLUGIN_DIRS`.

There is no default search path, no scan of the working directory, and no
attempt to be helpful about a directory nobody configured. An application
that searched `./plugins` by default would execute whatever happened to be in
the directory it was started from.

### 4.1 What this does not do

Discovery does not sandbox a plugin. Once loaded, plugin code runs with the
application's full privileges — which is what a plugin is. The control
offered here is over *whether* a directory is searched at all, and that
control is the operator's.

Configuring a plugin directory should be treated as equivalent to installing
software.

## 5. Loading

A file loads under a namespaced module name (`aet_plugin_<stem>`) so a plugin
cannot collide with, or shadow, an installed package.

### 5.1 Packages get search locations and a `sys.modules` entry

A package is loaded with its own `submodule_search_locations` and registered
in `sys.modules` before execution.

Both are required for the ordinary way to write a package — define the plugin
in `rules.py`, re-export it from `__init__.py`. Without them, relative
imports do not resolve and such a package fails to load entirely, which the
first implementation here did. A package whose execution fails is removed
from `sys.modules` again, so no half-executed module is left for a later
import to find.

### 5.2 A source contributes only what it defines

A module contributes the concrete `Plugin` subclasses defined by it or, for a
package, by its own submodules. A class merely imported from elsewhere is not
registered, so importing another plugin does not register somebody else's
twice, and importing the abstract `Plugin` base registers nothing.

Plugins are constructed with no arguments. A plugin needing configuration
receives it through `PluginContext` at activation, which is the contract
SDS-002 §10.3 already defines.

## 6. Failure Is Isolated And Reported

One plugin must not stop the others. A source that fails to import, a plugin
that fails to construct, and a plugin the runtime rejects are each recorded
with a reason, and discovery continues.

The rejection reason travels in the report rather than only to the log,
because a plugin silently absent is indistinguishable from a plugin that was
never configured.

### 6.1 A configured directory that does not exist is reported

A named directory that is missing is listed, not skipped. A mistyped path
would otherwise look exactly like a directory holding no plugins.

## 7. Acceptance Criteria

SDS-014 is satisfied when:

1. A plugin module in a configured directory is loaded, registered, and its
   extension reachable through the runtime.
2. Nothing is searched when no directory is configured, and a configured
   directory that does not exist is reported.
3. A source failing to import, a plugin failing to construct, and a plugin
   the runtime rejects are each recorded with a reason while other plugins
   still load.
4. A package may define its plugin in a submodule and re-export it, and a
   class imported from elsewhere is not registered.
5. A package that fails to execute leaves no entry in `sys.modules`.
6. The application service discovers from its configuration, and leaves an
   injected runtime alone.
7. All behavior above is covered by tests; `pytest`, `ruff`, `black`, and
   `mypy` pass.
