"""One option row: name/description plus the control for its type."""

from __future__ import annotations

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from .factory import build_widget


class OptionRow(Gtk.Box):
    """Full row for one option: heading line and input control below."""

    def __init__(self, spec, on_change: Optional[Callable[[str], None]] = None,
                 choices: Optional[List[str]] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("option-row")
        self.spec = spec
        self._on_change = on_change or (lambda _key: None)
        self._suppress = False

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.append(Gtk.Label(label=spec.label, xalign=0.0, wrap=True,
                                css_classes=["heading"]))
        header.append(Gtk.Label(label=":", xalign=0.0, css_classes=["dim-label"]))
        header.append(Gtk.Label(label=spec.description, xalign=0.0, wrap=True,
                                hexpand=True, css_classes=["dim-label"]))
        self.append(header)

        self._input = build_widget(spec, self._on_value_changed, choices=choices)
        self.append(self._input)

    def connect_changed(self, callback: Callable[[str], None]) -> None:
        """Set the callback invoked with the option key after a user change."""
        self._on_change = callback

    def _on_value_changed(self, *_):
        if not self._suppress:
            self._on_change(self.spec.key)

    def set_value(self, value) -> None:
        """Set the control value; invalid values are ignored."""
        try:
            self._input.set_value(value)
        except (TypeError, ValueError):
            return
        if not self._suppress:
            self._on_change(self.spec.key)

    def get_value(self):
        return self._input.get_value()

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the row; the theme styles the insensitive state."""
        self.set_sensitive(enabled)
