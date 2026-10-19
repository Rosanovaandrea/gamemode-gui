"""Descriptor of a single configuration option.

This is the small, GTK-free contract between the sections and the widget kit:
each section defines its own options as a list of :class:`OptionSpec`, the
section core renders/parses them, and the section view hands them to the widgets.
Keeping it GTK-free lets the section logic run headless.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from gamemode_gui.i18n import tr


@dataclass(frozen=True)
class OptionSpec:
    """Description of one option: its key, type, default and UI metadata."""

    key: str
    type: str
    default: Any = None
    description_id: str = ""
    label_id: Optional[str] = None
    widget: str = "entry"
    choices: Optional[List[str]] = None
    choice_labels: Optional[Dict[str, str]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    on_value: Optional[str] = None
    depends_on: Optional[str] = None
    comment: str = ""
    target: Optional[str] = None
    entry: Optional[str] = None
    special: bool = False
    special_source: Optional[str] = None

    @property
    def label(self) -> str:
        """Visible name, translated on access."""
        return tr(self.label_id) if self.label_id else self.key

    @property
    def description(self) -> str:
        """Visible description, translated on access."""
        return tr(self.description_id)

    @property
    def template(self) -> str:
        """INI line template for this key, e.g. ``reaper_freq={value}``."""
        return f"{self.key}={{value}}"
