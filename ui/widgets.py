"""Widgets built declaratively from an :class:`OptionSpec`.

Every option is rendered as a *row* with:

* a "Includi" checkbox bound to the activation flag,
* an input widget appropriate to the option type,
* a tooltip holding the description.

When the "Includi" checkbox is toggled on, the input widget becomes
editable. Editing a value automatically enables the flag; the user can still
explicitly uncheck "Includi" to keep the option out of the file.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from gi.repository import Adw, Gtk

from core.options_table import OptionSpec

ChangeCallback = Callable[[str], None]


class ListEditor(Gtk.Box):
    """A small editor for repeated-key list options."""

    def __init__(self, spec: OptionSpec) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.section = spec.section
        self.key = spec.key
        self._items: List[str] = []

        entry_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry(placeholder_text="Nuovo valore…")
        self.entry.set_hexpand(True)
        add_btn = Gtk.Button(label="Aggiungi")
        add_btn.add_css_class("suggested-action")
        entry_bar.append(self.entry)
        entry_bar.append(add_btn)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")

        self.append(entry_bar)
        self.append(self.listbox)

        add_btn.connect("clicked", self._on_add)
        self.entry.connect("activate", self._on_add)

    def _on_add(self, *_):
        text = self.entry.get_text().strip()
        if text:
            self._add_item(text)
            self.entry.set_text("")

    def _add_item(self, text: str) -> None:
        self._items.append(text)
        self._render()
        self._emit_change()

    def _remove_item(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._render()
            self._emit_change()

    def _emit_change(self) -> None:
        cb = getattr(self, "_on_change_cb", None)
        if cb:
            cb()

    def _render(self) -> None:
        # clear
        while (child := self.listbox.get_first_child()) is not None:
            self.listbox.remove(child)

        for i, item in enumerate(self._items):
            row = Adw.ActionRow(title=item)
            rm = Gtk.Button(icon_name="edit-delete-symbolic")
            rm.add_css_class("flat")
            rm.set_tooltip_text("Rimuovi")
            rm.connect("clicked", lambda _b, idx=i: self._remove_item(idx))
            row.add_suffix(rm)
            self.listbox.append(row)

        self.listbox.show()

    # -- value API --------------------------------------------------------
    def get_value(self) -> List[str]:
        return list(self._items)

    def set_value(self, items: List[str]) -> None:
        self._items = [str(i) for i in items]
        self._render()

    def clear(self) -> None:
        self._items = []
        self._render()


def _build_list_row_box(spec: OptionSpec) -> ListEditor:
    return ListEditor(spec)


class OptionRow(Gtk.Box):
    """One declarative row wrapping the include checkbox and the input."""

    def __init__(self, spec: OptionSpec, on_change: Optional[ChangeCallback] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._on_change = on_change or (lambda _sid: None)
        self.spec = spec
        self._suppress = False
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.include = Gtk.CheckButton(label="Includi")
        self.include.set_tooltip_text(f"Includi {spec.key} nel file di configurazione")
        title = Gtk.Label(label=spec.key, xalign=0.0, hexpand=True, wrap=True)
        title.set_tooltip_text(spec.description)
        bar.append(self.include)
        bar.append(title)
        self.append(bar)

        # Input widget
        self._input = self._build_input(spec)
        self.append(self._input)

        # Wire value-change detection per widget type (signals differ).
        self.include.connect("toggled", self._on_include_toggled)
        self._connect_changed(self._input, spec.type)

        # Allow the caller to set the initial state without firing change events.
        self._suppress = True
        self.set_include(False)

    _CHANGED_SIGNAL = {
        "int": "notify::value",
        "float": "notify::value",
        "bool": "notify::active",
        "choice": "notify::selected",
        "string": "changed",
    }

    def _connect_changed(self, widget, kind: str):
        if kind == "list":
            # ListEditor calls back manually after adding/removing items.
            widget._on_change_cb = self._on_value_changed
            return
        signal = self._CHANGED_SIGNAL.get(kind, "changed")
        widget.connect(signal, lambda *_: self._on_value_changed())

    # -- widget construction ------------------------------------------------
    def _build_input(self, spec: OptionSpec):
        t = spec.type
        if t == "int":
            return self._build_spin(spec, digit=False)
        if t == "float":
            return self._build_spin(spec, digit=True)
        if t == "bool":
            sw = Gtk.Switch(active=bool(spec.default))
            sw.add_css_class("h5")
            return sw
        if t == "choice":
            return self._build_combo(spec)
        if t == "list":
            return _build_list_row_box(spec)
        # string / fallback
        entry = Adw.EntryRow(show_apply_button=False)
        entry.set_text(str(spec.default))
        return entry

    def _build_spin(self, spec: OptionSpec, digit: bool):
        lo, hi = self._range(spec)
        step = 0.1 if digit else 1
        adj = Gtk.Adjustment(
            value=float(spec.default or 0), lower=lo, upper=hi, step_increment=step
        )
        spin = Adw.SpinRow(adjustment=adj)
        if digit:
            spin.set_digits(2)
        spin.set_value(float(spec.default or 0))
        return spin

    def _range(self, spec: OptionSpec):
        lo = spec.min_value if spec.min_value is not None else -1_000_000
        hi = spec.max_value if spec.max_value is not None else 1_000_000
        if hi <= lo:
            hi = lo + 1
        return lo, hi

    def _build_combo(self, spec: OptionSpec):
        choices = list(spec.choices or [])
        # For options that may legitimately be "unset" (e.g. defaultgov) we
        # prepend an empty choice mapping to "".
        self._unset = False
        if spec.default == "" or (spec.choices and "" in choices):
            self._unset = True
            choices = [""] + [c for c in choices if c != ""]

        self._model = Gtk.StringList.new(choices)
        combo = Adw.ComboRow(model=self._model)
        combo.set_title(spec.key)
        self._select_value(combo, choices, spec.default)
        return combo

    def _select_value(self, combo, choices, value):
        try:
            idx = choices.index(str(value))
        except ValueError:
            idx = 0
        combo.set_selected(idx)

    # -- event handling ---------------------------------------------------
    def _on_include_toggled(self, *_):
        enabled = self.include.get_active()
        self._set_input_sensitive(enabled)
        if not enabled and not self._suppress:
            # re-emit change so the controller disables affected options
            self._on_change(self.spec.id)

    def _on_value_changed(self, *_):
        # Editing a value automatically enables the flag.
        self.include.set_active(True)
        self._set_input_sensitive(True)
        if not self._suppress:
            self._on_change(self.spec.id)

    def _set_input_sensitive(self, sensitive: bool):
        sensitive = bool(sensitive)
        if self.spec.type != "list":
            self._input.set_sensitive(sensitive)
        else:
            self._input.set_sensitive(sensitive)

    # -- public value/state API -------------------------------------------
    def set_include(self, enabled: bool):
        self.include.set_active(bool(enabled))
        self._set_input_sensitive(bool(enabled))

    def get_include(self) -> bool:
        return self.include.get_active()

    def set_value(self, value) -> None:
        t = self.spec.type
        try:
            if t == "int":
                self._input.set_value(float(int(value)))
            elif t == "float":
                self._input.set_value(float(value))
            elif t == "bool":
                self._input.set_active(bool(value))
            elif t == "choice":
                choices = list(self.spec.choices or [])
                if self._unset:
                    choices = [""] + [c for c in choices if c != ""]
                self._select_value(self._input, choices, value)
            elif t == "list":
                self._input.set_value(list(value or []))
            else:  # string
                self._input.set_text(str(value))
        except (TypeError, ValueError):
            pass

    def get_value(self):
        t = self.spec.type
        if t == "int":
            return int(self._input.get_value())
        if t == "float":
            return self._input.get_value()
        if t == "bool":
            return self._input.get_active()
        if t == "choice":
            choices = list(self.spec.choices or [])
            if self._unset:
                choices = [""] + [c for c in choices if c != ""]
            idx = self._input.get_selected()
            return choices[idx]
        if t == "list":
            return self._input.get_value()
        # string
        return self._input.get_text()

    def set_editable(self, editable: bool) -> None:
        self._input.set_sensitive(editable)