"""Reusable option controls: choice, stepper, switch, list and CPU cores."""

from __future__ import annotations

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from i18n.translator import tr
from sections.serialization import expand_cpu_list


class ChoicePicker(Gtk.Box):
    """Radio buttons to choose one value among ``choices``."""

    def __init__(self, choices: List[str], on_change: Optional[Callable[[], None]] = None,
                 allow_unset: bool = False, labels: Optional[dict] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._on_change = on_change or (lambda: None)
        self._labels = dict(labels or {})
        self._buttons: List[Gtk.ToggleButton] = []
        self._values: List[str] = []
        self._selected: Optional[str] = None
        self._suppress = False

        self._flow = Gtk.FlowBox(max_children_per_line=8,
                                 selection_mode=Gtk.SelectionMode.NONE,
                                 column_spacing=4, row_spacing=4,
                                 valign=Gtk.Align.START, halign=Gtk.Align.START)
        self.append(self._flow)
        if allow_unset:
            self._add_button("", label=tr("choice.unset"))
        for choice in choices:
            self._add_button(choice)

    def _add_button(self, value: str, label: Optional[str] = None) -> None:
        btn = Gtk.ToggleButton(label=label or self._labels.get(value) or value)
        btn.add_css_class("choice-button")
        btn.set_group(self._buttons[0] if self._buttons else None)
        btn.connect("toggled", self._on_toggled, value)
        self._buttons.append(btn)
        self._values.append(value)
        self._flow.append(btn)

    def _on_toggled(self, btn: Gtk.ToggleButton, value: str) -> None:
        if self._suppress or not btn.get_active():
            return
        self._selected = value
        for other in self._buttons:
            if other is not btn:
                self._suppress = True
                other.set_active(False)
                self._suppress = False
        self._on_change()

    def get_value(self) -> str:
        return self._selected or ""

    def set_value(self, value) -> None:
        value = str(value or "")
        if value and value not in self._values:
            self._add_button(value)
        self._selected = value
        self._suppress = True
        for btn, choice_value in zip(self._buttons, self._values):
            btn.set_active(choice_value == value)
        self._suppress = False

    def set_sensitive(self, sensitive: bool) -> None:
        for btn in self._buttons:
            btn.set_sensitive(bool(sensitive))


class StepperBox(Gtk.Box):
    """Numeric field with ``-``/``+`` buttons and min/max bounds."""

    def __init__(self, value: float, min_value: Optional[float],
                 max_value: Optional[float], step: float = 1.0, digits: int = 0,
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._min = min_value if min_value is not None else -1_000_000
        self._max = max_value if max_value is not None else 1_000_000
        self._step = step
        self._digits = digits
        self._on_change = on_change or (lambda: None)
        self._value = float(value)

        self.minus = Gtk.Button(label="−")
        self.minus.add_css_class("stepper-button")
        self.minus.set_tooltip_text(tr("stepper.decrease"))
        self.value_label = Gtk.Label(label=self._fmt(self._value),
                                     css_classes=["monospace"])
        self.value_label.set_hexpand(True)
        self.value_label.set_halign(Gtk.Align.CENTER)
        self.plus = Gtk.Button(label="+")
        self.plus.add_css_class("stepper-button")
        self.plus.set_tooltip_text(tr("stepper.increase"))
        self.append(self.minus)
        self.append(self.value_label)
        self.append(self.plus)
        self.minus.connect("clicked", lambda *_: self._change(-self._step))
        self.plus.connect("clicked", lambda *_: self._change(+self._step))

    def _fmt(self, value: float) -> str:
        return f"{value:.{self._digits}f}" if self._digits else str(int(round(value)))

    def _change(self, delta: float) -> None:
        candidate = max(self._min, min(self._max, self._value + delta))
        candidate = round(candidate / self._step) * self._step
        candidate = max(self._min, min(self._max, candidate))
        if candidate != self._value:
            self._value = candidate
            self.value_label.set_text(self._fmt(candidate))
            self._on_change()

    def get_value(self):
        return round(self._value, self._digits) if self._digits else int(round(self._value))

    def set_value(self, value) -> None:
        self._value = max(self._min, min(self._max, float(value)))
        self.value_label.set_text(self._fmt(self._value))

    def set_sensitive(self, sensitive: bool) -> None:
        self.minus.set_sensitive(bool(sensitive))
        self.plus.set_sensitive(bool(sensitive))


class SwitchBox(Gtk.Box):
    """Switch mapping a boolean or an ``on_value``/``off_value`` pair."""

    def __init__(self, active: bool = False, on_value: Optional[str] = None,
                 off_value=None, on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._on_value = on_value
        self._off_value = off_value if off_value is not None else False
        self._on_change = on_change or (lambda: None)
        self._suppress = False
        self.switch = Gtk.Switch(active=bool(active))
        self.switch.add_css_class("h5")
        self.switch.set_halign(Gtk.Align.START)
        self.switch.set_valign(Gtk.Align.CENTER)
        self.switch.connect("notify::active", self._on_toggled)
        self.append(self.switch)

    def _on_toggled(self, *_):
        if not self._suppress:
            self._on_change()

    def get_value(self):
        if self._on_value is not None:
            return self._on_value if self.switch.get_active() else self._off_value
        return self.switch.get_active()

    def set_value(self, value) -> None:
        self._suppress = True
        if self._on_value is not None:
            self.switch.set_active(str(value) == str(self._on_value))
        else:
            self.switch.set_active(bool(value))
        self._suppress = False

    def set_sensitive(self, sensitive: bool) -> None:
        self.switch.set_sensitive(bool(sensitive))


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
    """Multiple core selection via checkboxes."""

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
