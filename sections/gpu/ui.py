"""View of the GPU section: page with a warning banner and dependency gating."""

from __future__ import annotations

from typing import List

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from i18n import tr
from widgets import OptionRow
from sections.gpu.core import GpuCore

TAB_TITLE_ID = "tab.gpu"
TITLE_ID = "step.gpu.title"
SUBTITLE_ID = "step.gpu.subtitle"
BANNER_ID = "gpu.banner"


class GpuPage(Gtk.Box):
    """Page with all the ``[gpu]`` options and a warning banner."""

    def __init__(self, core: GpuCore) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.core = core
        self.rows: List[OptionRow] = []
        self.append(self._header())
        self.append(self._option_list())
        self.prepend(self._banner())
        self.refresh_gating()

    def _banner(self) -> Gtk.Widget:
        banner = Adw.Banner(title=tr(BANNER_ID))
        banner.add_css_class("error")
        return banner

    def _header(self) -> Gtk.Widget:
        """Build the page header: section title + subtitle."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label=tr(TITLE_ID), xalign=0.0, css_classes=["title-2"]))
        box.append(Gtk.Label(label=tr(SUBTITLE_ID), xalign=0.0,
                             css_classes=["dim-label"], wrap=True))
        return box

    def _option_list(self) -> Gtk.Widget:
        """Build the scrollable list with one row per option of the section."""
        scroller = Gtk.ScrolledWindow(vexpand=True)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        for spec in self.core.options:
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
        self.refresh_gating()

    def refresh_gating(self) -> None:
        for row in self.rows:
            if not row.spec.depends_on:
                continue
            dependency = next((spec for spec in self.core.options
                               if spec.key == row.spec.depends_on), None)
            row.set_enabled(self.core.is_active(dependency) if dependency else True)


def build_page(core):
    """Factory used by the general UI while gathering the section pages."""
    return GpuPage(core)
