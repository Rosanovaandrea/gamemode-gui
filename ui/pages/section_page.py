"""Section page built with standard Libadwaita preferences widgets."""

from __future__ import annotations

from typing import Iterable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from i18n.translator import tr
from ui.widgets.option_row import OptionRow, build_row


class SectionPage(Gtk.Box):
    """One preferences page generated from a section core's options."""

    def __init__(self, core, title_id: str, subtitle_id: str, *,
                 banner_id: Optional[str] = None,
                 card_title_id: Optional[str] = None,
                 card_types: Iterable[str] = (),
                 exclude_types: Iterable[str] = ()) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.core = core
        self.rows: List[OptionRow] = []
        self._card_types = tuple(card_types)
        self._exclude_types = tuple(exclude_types)

        if banner_id:
            banner = Adw.Banner(title=tr(banner_id))
            banner.add_css_class("error")
            self.append(banner)

        page = Adw.PreferencesPage()
        page.set_vexpand(True)
        if self._card_types and card_title_id:
            page.add(self._group(tr(card_title_id), self._card_types))
        page.add(self._group(tr(title_id), None, tr(subtitle_id),
                             self._exclude_types))
        self.append(page)
        self.refresh_gating()

    def _group(self, title: str, included_types, description: str = "",
               excluded_types: Iterable[str] = ()) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=title, description=description)
        for spec in self.core.options:
            if included_types is not None and spec.type not in included_types:
                continue
            if spec.type in excluded_types:
                continue
            group.add(self._make_row(spec).widget)
        return group

    def _make_row(self, spec) -> OptionRow:
        row = build_row(spec, self._on_row_change,
                        choices=self.core.allowed_values_for(spec))
        self._populate_row(row)
        self.rows.append(row)
        return row

    def _on_row_change(self, key: str) -> None:
        row = next(row for row in self.rows if row.spec.key == key)
        getattr(self.core, f"set_{key}")(row.get_value())

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
