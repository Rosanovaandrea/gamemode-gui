"""Reusable GTK widgets for the GUI.

This module collects the *building blocks* of the interface. The construction of
the control for an option is centralised in :func:`build_widget`: the widget is
chosen from the fields of the JSON definition (``value_type`` / ``widget``), so no
per-option code is needed. The only difference for "special" values is in
``core.resolve_choices`` (the values come from the system), but the widget stays
standard.

It contains:

  * :func:`build_widget`  — standard control per type (stepper/switch/radio/list/entry)
  * :class:`ChoicePicker` — single choice WITHOUT dropdown: radio buttons in a FlowBox
  * :class:`StepperBox`   — numeric value with "-" and "+", bounded by min/max
  * :class:`SwitchBox`    — on/off switch with the same value interface
  * :class:`ListEditor`   — list editor (e.g. custom start/end scripts)
  * :class:`CoresEditor`  — CPU core selection (checkboxes)
  * :class:`OptionRow`    — full row: "name: description" + control below

All expose the same value interface: ``get_value()`` / ``set_value(v)`` /
``set_sensitive(b)`` and an ``on_change`` callback.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

import core
from core import tr


# ===========================================================================
# Single choice with radio buttons (no dropdown)
# ===========================================================================
class ChoicePicker(Gtk.Box):
    """Group of radio buttons to choose ONE value among ``choices``."""

    def __init__(
        self,
        choices: List[str],
        on_change: Optional[Callable[[], None]] = None,
        allow_unset: bool = False,
        labels: Optional[dict] = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._on_change = on_change or (lambda: None)
        self._labels = dict(labels or {})
        self._buttons: List[Gtk.ToggleButton] = []
        self._values: List[str] = []
        self._selected: Optional[str] = None
        self._suppress = False

        self._flow = Gtk.FlowBox(
            max_children_per_line=8,
            selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=4,
            row_spacing=4,
            valign=Gtk.Align.START,
            halign=Gtk.Align.START,
        )
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
        if self._suppress:
            return
        if not btn.get_active():
            return
        self._selected = value
        for other in self._buttons:
            if other is not btn:
                self._suppress = True
                other.set_active(False)
                self._suppress = False
        self._on_change()

    # -- Value API -----------------------------------------------------------
    def get_value(self) -> str:
        return self._selected or ""

    def set_value(self, value) -> None:
        value = str(value or "")
        # The current value may not be among the choices (e.g. a governor that is
        # no longer available): add it so it can still be shown.
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


# ===========================================================================
# Numeric stepper (- / + buttons with min and max)
# ===========================================================================
class StepperBox(Gtk.Box):
    """Numeric field with "-" and "+" buttons, bounded between ``min`` and ``max``."""

    def __init__(
        self,
        value: float,
        min_value: Optional[float],
        max_value: Optional[float],
        step: float = 1.0,
        digits: int = 0,
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
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
        self.value_label = Gtk.Label(label=self._fmt(self._value), css_classes=["monospace"])
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
        if self._digits:
            return f"{value:.{self._digits}f}"
        return str(int(round(value)))

    def _change(self, delta: float) -> None:
        new = self._value + delta
        new = max(self._min, min(self._max, new))
        new = round(new / self._step) * self._step
        new = max(self._min, min(self._max, new))
        if new != self._value:
            self._value = new
            self.value_label.set_text(self._fmt(new))
            self._on_change()

    # -- Value API -----------------------------------------------------------
    def get_value(self):
        if self._digits:
            return round(self._value, self._digits)
        return int(round(self._value))

    def set_value(self, value) -> None:
        self._value = max(self._min, min(self._max, float(value)))
        self.value_label.set_text(self._fmt(self._value))

    def set_sensitive(self, sensitive: bool) -> None:
        self.minus.set_sensitive(bool(sensitive))
        self.plus.set_sensitive(bool(sensitive))


# ===========================================================================
# On/off switch with a uniform interface (get_value/set_value)
# ===========================================================================
class SwitchBox(Gtk.Box):
    """Switch with the same interface as the other inputs.

    With ``on_value``/``off_value`` it maps the state to text values (type
    "enable": on -> ``on_value``, off -> ``off_value``). Without them, the value
    is a plain boolean (types "bool" and "toggle_entry").
    """

    def __init__(
        self,
        active: bool = False,
        on_value: Optional[str] = None,
        off_value=None,
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
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

    # -- Value API -----------------------------------------------------------
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


# ===========================================================================
# List editor (repeated keys: e.g. custom start/end scripts)
# ===========================================================================
class ListEditor(Gtk.Box):
    """Editor for list-type options (keys repeated in the INI file)."""

    def __init__(
        self,
        on_change: Optional[Callable[[], None]] = None,
        placeholder: str = tr("list.placeholder"),
    ) -> None:
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
        for i, item in enumerate(self._items):
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            lbl = Gtk.Label(label=item, xalign=0.0, hexpand=True, wrap=True)
            rm = Gtk.Button(icon_name="edit-delete-symbolic")
            rm.add_css_class("flat")
            rm.set_tooltip_text(tr("list.remove.tooltip"))
            rm.connect("clicked", lambda _b, idx=i: self._remove_item(idx))
            hbox.append(lbl)
            hbox.append(rm)
            row.set_child(hbox)
            self.listbox.append(row)

    # -- Value API -----------------------------------------------------------
    def get_value(self) -> List[str]:
        return list(self._items)

    def set_value(self, items: List[str]) -> None:
        self._items = [str(i) for i in items]
        self._render()

    def set_sensitive(self, sensitive: bool) -> None:
        self.entry.set_sensitive(bool(sensitive))


# ===========================================================================
# Core selector (checkboxes) for CPU pinning
# ===========================================================================
class CoresEditor(Gtk.Box):
    """Multiple core selection via checkboxes.

    The available cores come from the system (``special_source: cpu_cores``).
    The value is the sorted list of selected cores (e.g. ``[0, 2, 4]``).
    """

    def __init__(
        self,
        cores: List[str],
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._on_change = on_change or (lambda: None)
        self._suppress = False
        self._checks: dict = {}

        flow = Gtk.FlowBox(
            max_children_per_line=16,
            selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=8,
            row_spacing=4,
            valign=Gtk.Align.START,
            halign=Gtk.Align.START,
        )
        for core in cores:
            key = str(core)
            chk = Gtk.CheckButton(label=key)
            chk.connect("toggled", self._on_toggled)
            flow.append(chk)
            self._checks[key] = chk
        self.append(flow)

    def _on_toggled(self, *_):
        if not self._suppress:
            self._on_change()

    # -- Value API -----------------------------------------------------------
    def get_value(self) -> List[int]:
        return sorted(int(core) for core, chk in self._checks.items()
                      if chk.get_active())

    def set_value(self, values) -> None:
        if values is None:
            values = []
        if isinstance(values, (str, int)):
            values = core.expand_cpu_list(str(values))
        selected = {str(v) for v in values}
        self._suppress = True
        for core, chk in self._checks.items():
            chk.set_active(core in selected)
        self._suppress = False

    def set_sensitive(self, sensitive: bool) -> None:
        for chk in self._checks.values():
            chk.set_sensitive(bool(sensitive))


# ===========================================================================
# Standard control builder (no per-option ad-hoc code)
# ===========================================================================
def build_widget(spec, on_change: Callable[[], None]) -> Gtk.Widget:
    """Build the right control for an option.

    The value type and the widget are described in the JSON: here there is a
    single point that translates them into GTK. For special options only the
    "choices" change (resolved by ``core.resolve_choices``); the widget stays
    standard.
    """
    t = spec.type
    if t in ("int", "float"):
        is_float = t == "float"
        return StepperBox(
            value=float(spec.default or 0),
            min_value=spec.min_value,
            max_value=spec.max_value,
            step=0.1 if is_float else 1,
            digits=2 if is_float else 0,
            on_change=on_change,
        )
    if t in ("bool", "enable", "toggle_entry"):
        if t == "enable":
            return SwitchBox(
                active=str(spec.default) == str(spec.on_value),
                on_value=spec.on_value,
                off_value=spec.default,
                on_change=on_change,
            )
        return SwitchBox(active=bool(spec.default), on_change=on_change)
    if t == "choice":
        return ChoicePicker(
            choices=core.resolve_choices(spec),
            on_change=on_change,
            allow_unset=(spec.default == ""),
            labels=spec.choice_labels,
        )
    if t == "list":
        return ListEditor(on_change=on_change)
    if t == "cores":
        return CoresEditor(cores=core.resolve_choices(spec), on_change=on_change)
    # string / fallback
    entry = Gtk.Entry(text=str(spec.default))
    entry.connect("changed", lambda *_: on_change())
    return entry


# ===========================================================================
# Declarative row for an option ("name: description" + control below)
# ===========================================================================
class OptionRow(Gtk.Box):
    """Full row for an option of the JSON definition.

    Structure:
        <option name>: <description>   <- on a single, clearly visible line
        <input widget built per type>

    Behaviour:
      * the input is ALWAYS active and every change propagates the new value;
      * the description is shown next to the name (no tooltip/popup);
      * internal padding to give the rows room to breathe.
    """

    def __init__(
        self,
        spec,
        on_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self._on_change = on_change or (lambda _sid: None)
        self.spec = spec
        self._suppress = False

        # Top line: option name + description, separated by ":".
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title = Gtk.Label(label=spec.label, xalign=0.0, wrap=True,
                          css_classes=["heading"])
        sep = Gtk.Label(label=":", xalign=0.0, css_classes=["dim-label"])
        desc = Gtk.Label(label=spec.description, xalign=0.0, wrap=True,
                         hexpand=True, css_classes=["dim-label"])
        header.append(title)
        header.append(sep)
        header.append(desc)
        self.append(header)

        # Standard input widget, built from the definition type.
        self._input = build_widget(spec, self._on_value_changed)
        self.append(self._input)

    # -- signals -------------------------------------------------------------
    def _on_value_changed(self, *_):
        if not self._suppress:
            self._on_change(self.spec.id)

    # -- public API ----------------------------------------------------------
    def set_value(self, value) -> None:
        try:
            self._input.set_value(value)
        except (TypeError, ValueError):
            return
        if not self._suppress:
            self._on_change(self.spec.id)

    def get_value(self):
        return self._input.get_value()

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the row (used for dependent options)."""
        enabled = bool(enabled)
        self.set_sensitive(enabled)
        self._input.set_sensitive(enabled)
        self.set_opacity(1.0 if enabled else 0.5)
