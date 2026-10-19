"""Compatibility shim for the old ``sections`` package.

All modules are aliased to their canonical ``gamemode_gui.sections`` objects so
``import sections.general.core`` and ``import gamemode_gui.sections.general.core``
return the exact same module (and therefore the same classes).
"""

import importlib
import sys

from gamemode_gui import sections as _real

sys.modules[__name__] = _real

_MODULES = (
    "core", "initializer",
    "general", "general.options", "general.core", "general.initializer",
    "gpu", "gpu.options", "gpu.core", "gpu.initializer",
    "cpu", "cpu.options", "cpu.core", "cpu.initializer",
    "custom", "custom.options", "custom.core", "custom.initializer",
    "presentation", "presentation.core",
    "daemon", "daemon.core",
)

for _name in _MODULES:
    sys.modules[f"{__name__}.{_name}"] = importlib.import_module(
        f"gamemode_gui.sections.{_name}")
