"""Build one standard Libadwaita row for an option."""

from __future__ import annotations

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from i18n.translator import tr
from spec import OptionSpec
from ui.widgets.controls import CoresEditor, ListEditor


class OptionRow:
    """Uniform value API around a standard ``Adw.PreferencesRow``."""

    def __init__(self, spec: OptionSpec,
                 on_change: Optional[Callable[[str], None]] = None) -> None:
        self.spec = spec
        self.widget: Adw.PreferencesRow = None
        self._on_change = on_change or (lambda _key: None)
        self._suppress = False
        self._get = lambda: None
        self._set = lambda _value: None

    def _notify(self, *_):
        if not self._suppress:
            self._on_change(self.spec.key)

    def get_value(self):
        return self._get()

    def set_value(self, value) -> None:
        was_suppressed = self._suppress
        self._suppress = True
        self._set(value)
        self._suppress = was_suppressed
        if not was_suppressed:
            self._on_change(self.spec.key)

    def set_enabled(self, enabled: bool) -> None:
        self.widget.set_sensitive(bool(enabled))

    def get_sensitive(self) -> bool:
        return self.widget.get_sensitive()


def build_row(spec: OptionSpec, on_change: Callable[[str], None],
              choices: Optional[List[str]] = None) -> OptionRow:
    """Create the standard row for ``spec.type``."""
    row = OptionRow(spec, on_change)
    available = list(choices) if choices is not None else list(spec.choices or [])
    match spec.type:
        case "bool" | "toggle_entry":
            _switch_row(row)
        case "enable":
            _enable_row(row)
        case "int" | "float":
            _spin_row(row)
        case "choice":
            _combo_row(row, available)
        case "list":
            _list_row(row)
        case "cores":
            _cores_row(row, available)
        case _:
            _entry_row(row)
    return row


def _switch_row(row: OptionRow) -> None:
    row.widget = Adw.SwitchRow(title=row.spec.label, subtitle=row.spec.description)
    row.widget.set_active(bool(row.spec.default))
    row.widget.connect("notify::active", row._notify)
    row._input = row.widget
    row._get = row.widget.get_active
    row._set = lambda value: row.widget.set_active(bool(value))


def _enable_row(row: OptionRow) -> None:
    row.widget = Adw.SwitchRow(title=row.spec.label, subtitle=row.spec.description)
    row.widget.set_active(str(row.spec.default) == str(row.spec.on_value))
    row.widget.connect("notify::active", row._notify)
    row._input = row.widget
    row._get = lambda: (row.spec.on_value if row.widget.get_active()
                        else row.spec.default)
    row._set = lambda value: row.widget.set_active(
        str(value) == str(row.spec.on_value))


def _spin_row(row: OptionRow) -> None:
    is_float = row.spec.type == "float"
    lower = row.spec.min_value if row.spec.min_value is not None else -1_000_000
    upper = row.spec.max_value if row.spec.max_value is not None else 1_000_000
    row.widget = Adw.SpinRow.new_with_range(lower, upper, 0.1 if is_float else 1)
    row.widget.set_digits(2 if is_float else 0)
    row.widget.set_title(row.spec.label)
    row.widget.set_subtitle(row.spec.description)
    row.widget.set_value(float(row.spec.default or 0))
    row.widget.connect("notify::value", row._notify)
    row._input = row.widget
    row._get = (lambda: round(row.widget.get_value(), 2) if is_float
                else int(round(row.widget.get_value())))
    row._set = lambda value: row.widget.set_value(float(value))


def _combo_row(row: OptionRow, choices: List[str]) -> None:
    values = list(choices)
    if row.spec.default == "" and "" not in values:
        values.insert(0, "")
    labels = row.spec.choice_labels or {}
    model = Gtk.StringList.new([
        labels.get(value, tr("choice.unset") if value == "" else value)
        for value in values
    ])
    row.widget = Adw.ComboRow(title=row.spec.label, subtitle=row.spec.description)
    row.widget.set_model(model)
    row.widget.connect("notify::selected", row._notify)
    row._input = row.widget
    row._get = lambda: (
        values[row.widget.get_selected()]
        if 0 <= row.widget.get_selected() < len(values) else "")
    row._set = lambda value: _select_combo(row.widget, values, model, value)


def _select_combo(combo: Adw.ComboRow, values: List[str], model: Gtk.StringList,
                  value) -> None:
    value = str(value or "")
    if value not in values:
        values.append(value)
        model.append(value)
    combo.set_selected(values.index(value))


def _list_row(row: OptionRow) -> None:
    row.widget = Adw.ExpanderRow(title=row.spec.label,
                                 subtitle=row.spec.description)
    row.widget.set_expanded(True)
    editor = ListEditor(on_change=row._notify)
    holder = Adw.PreferencesRow()
    holder.set_child(editor)
    row.widget.add_row(holder)
    row._input = editor
    row._get = editor.get_value
    row._set = editor.set_value


def _cores_row(row: OptionRow, cores: List[str]) -> None:
    row.widget = Adw.ExpanderRow(title=row.spec.label,
                                 subtitle=row.spec.description)
    row.widget.set_expanded(True)
    editor = CoresEditor(cores=cores, on_change=row._notify)
    holder = Adw.PreferencesRow()
    holder.set_child(editor)
    row.widget.add_row(holder)
    row._input = editor
    row._get = editor.get_value
    row._set = editor.set_value


def _entry_row(row: OptionRow) -> None:
    row.widget = Adw.ActionRow(title=row.spec.label,
                               subtitle=row.spec.description)
    entry = Gtk.Entry(text=str(row.spec.default or ""), valign=Gtk.Align.CENTER)
    entry.set_width_chars(20)
    entry.connect("changed", row._notify)
    row.widget.add_suffix(entry)
    row._input = entry
    row._get = entry.get_text
    row._set = entry.set_text
