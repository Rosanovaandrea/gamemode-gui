"""View of the Custom section: notification card + script list editors."""

from __future__ import annotations

from typing import List

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from i18n import tr
from widgets import OptionRow
from sections.custom.core import CustomCore

TAB_TITLE_ID = "tab.custom"
TITLE_ID = "step.custom.title"
SUBTITLE_ID = "step.custom.subtitle"
TOGGLE_CARD_ID = "custom.notifications.title"


class CustomPage(Gtk.Box):
    """Page with the ``[custom]`` options: a toggle card plus the list editors."""

    def __init__(self, core: CustomCore) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.core = core
        self.rows: List[OptionRow] = []
        self.append(self._header())
        self.append(self._toggle_card())
        self.append(self._option_list())

    def _header(self) -> Gtk.Widget:
        """Build the page header: section title + subtitle."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label=tr(TITLE_ID), xalign=0.0, css_classes=["title-2"]))
        box.append(Gtk.Label(label=tr(SUBTITLE_ID), xalign=0.0,
                             css_classes=["dim-label"], wrap=True))
        return box

    def _toggle_card(self) -> Gtk.Widget:
        """Card with the notification switches (the ``toggle_entry`` options)."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("card")
        for margin in ("top", "bottom", "start", "end"):
            getattr(card, f"set_margin_{margin}")(4)
        title = Gtk.Label(label=tr(TOGGLE_CARD_ID), xalign=0.0, css_classes=["heading"])
        title.set_margin_start(12)
        title.set_margin_top(8)
        title.set_margin_bottom(4)
        card.append(title)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        for spec in self.core.options:
            if spec.type == "toggle_entry":
                listbox.append(self._make_row(spec))
        card.append(listbox)
        return card

    def _option_list(self) -> Gtk.Widget:
        """Build the list of the non-toggle options (start/end/script_timeout)."""
        scroller = Gtk.ScrolledWindow(vexpand=True)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        for spec in self.core.options:
            # The toggle_entry options live in the notification card, not here.
            if spec.type != "toggle_entry":
                listbox.append(self._make_row(spec))
        scroller.set_child(listbox)
        return scroller

    def _make_row(self, spec) -> OptionRow:
        """Build one editable row, wired to the core's setter, and track it."""
        row = OptionRow(spec, choices=self.core.choices_for(spec))
        self._populate_row(row)
        # A change in the widget pushes the new value into the core.
        row._on_change = lambda _key, _row=row: self._on_row_change(_row)
        self.rows.append(row)
        return row

    def _on_row_change(self, row: OptionRow) -> None:
        """Push the widget value into the state through the speaking setter."""
        getattr(self.core, f"set_{row.spec.key}")(row.get_value())

    def _populate_row(self, row: OptionRow) -> None:
        """Sync a row with the state without propagating the change event."""
        row._suppress = True
        row.set_value(getattr(self.core, f"get_{row.spec.key}")())
        row._suppress = False

    def refresh(self) -> None:
        for row in self.rows:
            self._populate_row(row)


def build_page(core):
    """Factory used by the general UI while gathering the section pages."""
    return CustomPage(core)
