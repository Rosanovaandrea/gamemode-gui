"""In-memory session controller bridging the declarative table and the UI.

It owns the activation flags and the current values. The step pages read and
write through it, and its :meth:`render` produces the ``gamemode.ini`` text.
"""

from __future__ import annotations

from typing import Dict, Optional

from core.activation import ActivationManager
from core.options_table import OPTIONS
from core.renderer import render_ini


class SessionController:
    def __init__(self) -> None:
        self.activation = ActivationManager()
        self.values: Dict[str, object] = {spec.id: spec.default for spec in OPTIONS}
        self.on_change = None  # optional Callable[[], None] for dirty tracking

    # -- loading -------------------------------------------------------------
    def load(self, config_path: Optional[str]) -> None:
        """Seed flags/values from an existing file (or defaults)."""
        self.values = self.activation.rebuild_from_file(config_path)

    # -- update --------------------------------------------------------------
    def set_option(self, spec_id: str, value) -> None:
        self.values[spec_id] = value
        self.activation.enable(spec_id)
        if self.on_change:
            self.on_change()

    def set_include(self, spec_id: str, enabled: bool) -> None:
        self.activation.set_flag(spec_id, bool(enabled))
        if self.on_change:
            self.on_change()

    def get_value(self, spec_id: str):
        return self.values.get(spec_id)

    def is_active(self, spec_id: str) -> bool:
        return self.activation.get_flag(spec_id)

    # -- rendering -----------------------------------------------------------
    def render(self) -> str:
        flags = {spec.id: self.activation.get_flag(spec.id) for spec in OPTIONS}
        return render_ini(flags, self.values)