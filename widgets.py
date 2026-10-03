"""Widget GTK riutilizzabili per la GUI.

Questo modulo raccoglie i *building block* dell'interfaccia. La costruzione del
controllo per un'opzione è centralizzata in :func:`build_widget`: si sceglie il
widget in base ai campi della definizione JSON (``value_type`` / ``widget``), in
modo che non serva codice ad hoc per ogni opzione. Le uniche differenze per i
valori "speciali" stanno in ``core.resolve_choices`` (i valori arrivano dal
sistema), ma il widget resta standard.

Contiene:

  * :func:`build_widget`  — controllo standard per tipo (stepper/switch/radio/list/entry)
  * :class:`ChoicePicker` — scelta singola SENZA dropdown: radio button in un FlowBox
  * :class:`StepperBox`   — valore numerico con "-" e "+", vincolato a min/max
  * :class:`ListEditor`   — editor di liste (whitelist/blacklist)
  * :class:`OptionRow`    — riga completa: "nome: descrizione" + selettore sotto

Tutti espongono la stessa interfaccia valori: ``get_value()`` / ``set_value(v)``
/ ``set_sensitive(b)`` e un callback ``on_change``.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

import core
from core import tr


# ===========================================================================
# Scelta singola a pulsanti radio (niente dropdown)
# ===========================================================================
class ChoicePicker(Gtk.Box):
    """Gruppo di radio-button per scegliere UN valore tra ``choices``."""

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

    # -- API valori ----------------------------------------------------------
    def get_value(self) -> str:
        return self._selected or ""

    def set_value(self, value) -> None:
        value = str(value or "")
        # Il valore corrente potrebbe non essere tra le scelte (es. governor
        # non più disponibile): lo aggiungiamo per poterlo mostrare.
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
# Stepper numerico (pulsanti - / + con min e max)
# ===========================================================================
class StepperBox(Gtk.Box):
    """Campo numerico con pulsanti "-" e "+", vincolato tra ``min`` e ``max``."""

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
        self.minus.set_tooltip_text(tr("stepper.decrease"))
        self.value_label = Gtk.Label(label=self._fmt(self._value), css_classes=["monospace"])
        self.value_label.set_hexpand(True)
        self.value_label.set_halign(Gtk.Align.CENTER)
        self.plus = Gtk.Button(label="+")
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

    # -- API valori ----------------------------------------------------------
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
# Editor di liste (chiavi ripetute: whitelist/blacklist)
# ===========================================================================
class ListEditor(Gtk.Box):
    """Editor per opzioni di tipo lista (chiavi ripetute nel file INI)."""

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
        self.listbox.show()

    # -- API valori ---------------------------------------------------------
    def get_value(self) -> List[str]:
        return list(self._items)

    def set_value(self, items: List[str]) -> None:
        self._items = [str(i) for i in items]
        self._render()

    def set_sensitive(self, sensitive: bool) -> None:
        self.entry.set_sensitive(bool(sensitive))


# ===========================================================================
# Selettore di core (checkbox) per pinning CPU
# ===========================================================================
class CoresEditor(Gtk.Box):
    """Selezione multipla dei core tramite checkbox.

    I core disponibili arrivano dal sistema (``special_source: cpu_cores``).
    Il valore è la lista ordinata dei core selezionati (es. ``[0, 2, 4]``).
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

    # -- API valori ---------------------------------------------------------
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
# Builder standard del controllo (nessun codice ad hoc per opzione)
# ===========================================================================
def build_widget(spec, on_change: Callable[[], None]) -> Gtk.Widget:
    """Costruisce il controllo giusto per un'opzione.

    Il tipo del valore e il widget sono descritti nel JSON: qui c'è un unico
    punto che li traduce in GTK. Per le opzioni speciali cambiano solo le
    "choices" (risolte da ``core.resolve_choices``), il widget resta standard.
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
    if t in ("bool", "enable"):
        if t == "enable":
            active = str(spec.default) == str(spec.on_value)
        else:
            active = bool(spec.default)
        sw = Gtk.Switch(active=active)
        sw.add_css_class("h5")
        sw.set_halign(Gtk.Align.START)
        sw.set_valign(Gtk.Align.CENTER)
        sw.set_hexpand(False)
        sw.connect("notify::active", lambda *_: on_change())
        return sw
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
# Riga dichiarativa per un'opzione ("nome: descrizione" + selettore sotto)
# ===========================================================================
class OptionRow(Gtk.Box):
    """Riga completa per un'opzione della definizione JSON.

    Struttura:
        <nome opzione>: <descrizione>   <- su una sola riga, ben visibile
        <widget input costruito per tipo>

    Comportamento:
      * l'input è SEMPRE attivo e ogni modifica propaga il nuovo valore;
      * la descrizione è mostrata accanto al nome (niente tooltip/popup);
      * padding interno per dare respiro tra una riga e l'altra.
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

        # Riga alta: nome opzione + descrizione, separati da ":".
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

        # Widget input standard, costruito dal tipo della definizione.
        self._input = build_widget(spec, self._on_value_changed)
        self.append(self._input)

    # -- segnali --------------------------------------------------------------
    def _on_value_changed(self, *_):
        if not self._suppress:
            self._on_change(self.spec.id)

    # -- API pubblica ----------------------------------------------------------
    def set_value(self, value) -> None:
        try:
            if self.spec.type in ("bool", "enable"):
                if self.spec.type == "enable":
                    self._input.set_active(str(value) == str(self.spec.on_value))
                else:
                    self._input.set_active(bool(value))
            else:
                self._input.set_value(value)
        except (TypeError, ValueError):
            return
        if not self._suppress:
            self._on_change(self.spec.id)

    def get_value(self):
        if self.spec.type == "bool":
            return self._input.get_active()
        if self.spec.type == "enable":
            if self._input.get_active():
                return self.spec.on_value
            return self.spec.default
        return self._input.get_value()

    def set_enabled(self, enabled: bool) -> None:
        """Attiva/disattiva la riga (usato per le opzioni dipendenti)."""
        enabled = bool(enabled)
        self.set_sensitive(enabled)
        self._input.set_sensitive(enabled)
        self.set_opacity(1.0 if enabled else 0.5)
