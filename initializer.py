"""Application bootstrap: create the sections and load them from the file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import i18n
from configuration import Configuration, resolve_base_path, resolve_config_path
from core import AppCore
from sections.cpu.core import CpuCore
from sections.custom.core import CustomCore
from sections.general.core import GeneralCore
from sections.gpu.core import GpuCore
from state import AppStore

# The order is the tab order.
SECTION_CLASSES = (GeneralCore, GpuCore, CpuCore, CustomCore)


@dataclass
class App:
    """Everything the UI needs: the general core and the resolved paths."""

    core: AppCore
    config_path: str
    base_path: Optional[str]


def build_app(config_path: Optional[str] = None) -> App:
    """Build the application state and load every section from disk."""
    config_path = config_path or resolve_config_path()
    store = AppStore()
    sections = [core_class(store=store) for core_class in SECTION_CLASSES]
    configuration = Configuration(config_path, resolve_base_path())
    configuration.load(sections)
    app_core = AppCore(configuration, sections, store)
    configuration.ensure_orig()
    store.set_dirty(False)
    i18n.ensure_settings()
    return App(core=app_core, config_path=config_path,
               base_path=app_core.base_path)


def reload(app: App) -> None:
    """Reload every section from the files currently on disk."""
    app.core.configuration.load(app.core.sections)
    if app.core.store is not None:
        app.core.store.set_dirty(False)


__all__ = ["App", "SECTION_CLASSES", "build_app", "reload"]
