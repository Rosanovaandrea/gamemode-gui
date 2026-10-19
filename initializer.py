"""General initializer: builds the state and wires the sections.

It reads the two configuration texts once (the installed base and the ``/etc``
override, or the saved session if neither exists), then asks every section
initializer to load its own slice into its own state. It also ensures the
language settings and the pristine ``.orig`` baseline exist, and owns the reload
used after a restore.

Adding a stateful section is one entry in :data:`SECTION_MODULES` plus its
package (``core.py`` / ``ui.py`` / ``initializer.py``). The UI modules are
imported by the window, not here, so this stays headless.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import i18n
from core import AppCore
from config import load_session, read_text, resolve_base_path, resolve_config_path
from state import AppStore
from sections.cpu import initializer as cpu_initializer
from sections.cpu.core import CpuCore
from sections.custom import initializer as custom_initializer
from sections.custom.core import CustomCore
from sections.general import initializer as general_initializer
from sections.general.core import GeneralCore
from sections.gpu import initializer as gpu_initializer
from sections.gpu.core import GpuCore

# section id -> (core class, initializer module). The order is the tab order.
SECTION_MODULES = {
    "general": (GeneralCore, general_initializer),
    "gpu": (GpuCore, gpu_initializer),
    "cpu": (CpuCore, cpu_initializer),
    "custom": (CustomCore, custom_initializer),
}

__all__ = ["App", "SECTION_MODULES", "build_app", "reload"]


@dataclass
class App:
    """Everything the UI needs: the general core and the resolved paths."""

    core: AppCore
    config_path: str
    base_path: Optional[str]


def _configuration_texts(config_path: str) -> Tuple[str, str, Optional[Dict[str, object]]]:
    """Read the base and override texts.

    The session is a fallback used only when there is nothing at all to read
    (the override file does not exist and no installed base is available), so a
    restore that leaves the file empty resets the sections to their defaults
    instead of resurrecting the last session.
    """
    base_path = resolve_base_path()
    base_text = read_text(base_path)
    override_text = read_text(config_path)
    session_values: Optional[Dict[str, object]] = None
    if not os.path.isfile(config_path) and base_path is None:
        session_values = load_session(config_path)
    return base_text, override_text, session_values


def _build_sections(base_text: str, override_text: str,
                    session_values: Optional[Dict[str, object]],
                    store: AppStore) -> List:
    """Create and initialize every section core."""
    sections: List = []
    for _section_id, (core_class, initializer_module) in SECTION_MODULES.items():
        section_core = core_class(store=store)
        initializer_module.initialize(section_core, base_text, override_text,
                                      session_values)
        sections.append(section_core)
    return sections


def build_app(config_path: Optional[str] = None) -> App:
    """Build the whole application state, ready for the UI."""
    config_path = config_path or resolve_config_path()
    base_text, override_text, session_values = _configuration_texts(config_path)
    store = AppStore()
    sections = _build_sections(base_text, override_text, session_values, store)

    # The pristine baseline is the active file as it was (empty on a fresh
    # install); seeding it with the base would duplicate list values on a
    # factory reset, because the daemon already merges the base with /etc.
    app_core = AppCore(config_path=config_path, base_path=resolve_base_path(),
                       sections=sections, orig_seed="", store=store)
    app_core.config_manager.ensure_orig_on_first_run("")
    store.set_dirty(False)
    i18n.ensure_settings()
    return App(core=app_core, config_path=config_path,
               base_path=app_core.base_path)


def reload(app: App) -> None:
    """Reload every section state from the files currently on disk."""
    base_text, override_text, session_values = _configuration_texts(app.config_path)
    for section_core in app.core.sections:
        initializer_module = SECTION_MODULES[section_core.section_id][1]
        initializer_module.initialize(section_core, base_text, override_text,
                                      session_values)
    if app.core.store is not None:
        app.core.store.set_dirty(False)
