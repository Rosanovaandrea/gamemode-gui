"""Generic section page: header, optional card/banner and editable rows."""

from __future__ import annotations

from typing import Iterable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from i18n import tr
from ui.widgets import OptionRow


class SectionPage(Gtk.Box):
    """Page built from a section core's options."""

    def __init__(self, core, title_id: str, subtitle_id: str, *,
                 banner_id: Optional[str] = None,
                 card_title_id: Optional[str] = None,
                 card_types: Iterable[str] = (),
                 exclude_types: Iterable[str] = ()) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.core = core
        self.rows: List[OptionRow] = []
        self._card_types = tuple(card_types)
        self._exclude_types = tuple(exclude_types)

        if banner_id:
            banner = Adw.Banner(title=tr(banner_id))
            banner.add_css_class("error")
            self.append(banner)
        self.append(self._header(title_id, subtitle_id))
        if self._card_types and card_title_id:
            self.append(self._card(card_title_id))
        self.append(self._option_list())
        self.refresh_gating()

    def _header(self, title_id: str, subtitle_id: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label=tr(title_id), xalign=0.0, css_classes=["title-2"]))
        box.append(Gtk.Label(label=tr(subtitle_id), xalign=0.0,
                             css_classes=["dim-label"], wrap=True))
        return box

    def _card(self, title_id: str) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("card")
        for margin in ("top", "bottom", "start", "end"):
            getattr(card, f"set_margin_{margin}")(4)
        title = Gtk.Label(label=tr(title_id), xalign=0.0, css_classes=["heading"])
        title.set_margin_start(12)
        title.set_margin_top(8)
        title.set_margin_bottom(4)
        card.append(title)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        for spec in self.core.options:
            if spec.type in self._card_types:
                listbox.append(self._make_row(spec))
        card.append(listbox)
        return card

    def _option_list(self) -> Gtk.Widget:
        scroller = Gtk.ScrolledWindow(vexpand=True)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        for spec in self.core.options:
            if spec.type not in self._card_types and spec.type not in self._exclude_types:
                listbox.append(self._make_row(spec))
        scroller.set_child(listbox)
        return scroller

    def _make_row(self, spec) -> OptionRow:
        row = OptionRow(spec, choices=self.core.allowed_values_for(spec))
        self._populate_row(row)
        row.connect_changed(
            lambda _key, current=row: getattr(
                self.core, f"set_{current.spec.key}")(current.get_value()))
        self.rows.append(row)
        return row

    def _populate_row(self, row: OptionRow) -> None:
        row._suppress = True
        row.set_value(getattr(self.core, f"get_{row.spec.key}")())
        row._suppress = False

    def refresh(self) -> None:
        for row in self.rows:
            self._populate_row(row)
        self.refresh_gating()

    def refresh_gating(self) -> None:
        for row in self.rows:
            if row.spec.depends_on:
                dependency = next((spec for spec in self.core.options
                                   if spec.key == row.spec.depends_on), None)
                row.set_enabled(self.core.is_option_active(dependency)
                                if dependency else True)
