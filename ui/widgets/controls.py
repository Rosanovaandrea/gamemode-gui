"""Editors for option types that need more than a standard row."""

from __future__ import annotations

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from i18n.translator import tr
from sections.serialization import expand_cpu_list


class ListEditor(Gtk.Box):
    """Editor for repeated-key list options."""

    def __init__(self, on_change: Optional[Callable[[], None]] = None,
                 placeholder: str = tr("list.placeholder")) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._items: List[str] = []
        self._on_change = on_change or (lambda: None)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry(placeholder_text=placeholder)
        self.entry.set_hexpand(True)
        add_btn = Gtk.Button(label=tr("list.add"))
        add_btn.add_css_class("suggested-action")
        bar.append(self.entry)
        bar.append(add_btn)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.append(bar)
        self.append(self.listbox)
        add_btn.connect("clicked", self._on_add)
        self.entry.connect("activate", self._on_add)

    def _on_add(self, *_):
        text = self.entry.get_text().strip()
        if text:
            self._items.append(text)
            self.entry.set_text("")
            self._render()
            self._on_change()

    def _remove_item(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._render()
            self._on_change()

    def _render(self) -> None:
        while (child := self.listbox.get_first_child()) is not None:
            self.listbox.remove(child)
        for index, item in enumerate(self._items):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.append(Gtk.Label(label=item, xalign=0.0, hexpand=True, wrap=True))
            remove = Gtk.Button(icon_name="edit-delete-symbolic")
            remove.add_css_class("flat")
            remove.set_tooltip_text(tr("list.remove.tooltip"))
            remove.connect("clicked", lambda _b, i=index: self._remove_item(i))
            box.append(remove)
            row.set_child(box)
            self.listbox.append(row)

    def get_value(self) -> List[str]:
        return list(self._items)

    def set_value(self, items: List[str]) -> None:
        self._items = [str(item) for item in items]
        self._render()

    def set_sensitive(self, sensitive: bool) -> None:
        self.entry.set_sensitive(bool(sensitive))


class CoresEditor(Gtk.Box):
    """Multiple core selection via standard check buttons."""

    def __init__(self, cores: List[str],
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._on_change = on_change or (lambda: None)
        self._suppress = False
        self._checks: dict = {}
        flow = Gtk.FlowBox(max_children_per_line=16,
                           selection_mode=Gtk.SelectionMode.NONE,
                           column_spacing=8, row_spacing=4,
                           valign=Gtk.Align.START, halign=Gtk.Align.START)
        for core in cores:
            key = str(core)
            check = Gtk.CheckButton(label=key)
            check.connect("toggled", self._on_toggled)
            flow.append(check)
            self._checks[key] = check
        self.append(flow)

    def _on_toggled(self, *_):
        if not self._suppress:
            self._on_change()

    def get_value(self) -> List[int]:
        return sorted(int(core) for core, check in self._checks.items()
                      if check.get_active())

    def set_value(self, values) -> None:
        if values is None:
            values = []
        if isinstance(values, (str, int)):
            values = expand_cpu_list(str(values))
        selected = {str(value) for value in values}
        self._suppress = True
        for core, check in self._checks.items():
            check.set_active(core in selected)
        self._suppress = False

    def set_sensitive(self, sensitive: bool) -> None:
        for check in self._checks.values():
            check.set_sensitive(bool(sensitive))
