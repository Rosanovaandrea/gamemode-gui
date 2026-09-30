"""Widget GTK riutilizzabili per la GUI.

Questo modulo raccoglie in un unico posto i *building block* che l'interfaccia
usa per ogni tipo di opzione; così possono essere riutilizzati ovunque senza
duplicare codice (per la gestione di più step, per future finestre, ecc.).

Contiene:

  * :class:`ChoicePicker`   — scelta singola SENZA dropdown: un gruppo di
                             pulsanti radio in un FlowBox. Selezionare una voce
                             disattiva le altre (come richiesto). Niente popup
                             => niente problemi di posizionamento dei menù.
  * :class:`StepperBox`     — valore numerico con pulsanti "-" e "+",
                             vincolato a min/max (per ioprio, renice, ecc.).
  * :class:`ListEditor`     — editor di liste (whitelist/blacklist).
  * :class:`OptionRow`      — riga dichiarativa completa: checkbox "Includi" +
                             widget costruito in base al tipo della spec.

Tutti questi widget espongono la stessa interfaccia valori:
``get_value()`` / ``set_value(v)`` / ``set_sensitive(b)`` e un callback
``on_change`` invocato quando l'utente modifica il valore.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from gi.repository import Gtk

from core import tr


# ===========================================================================
# Scelta singola a pulsanti radio (niente dropdown)
# ===========================================================================
class ChoicePicker(Gtk.Box):
    """Gruppo di radio-button per scegliere UN valore tra ``choices``.

    Ogni voce è un ``Gtk.ToggleButton``; togglare una voce disattiva
    automaticamente le altre (comportamento radio), quindi l'utente non deve
    mai aprire un menù a tendina. Il callback ``on_change`` è chiamato col
    valore selezionato.
    """

    def __init__(
        self,
        choices: List[str],
        on_change: Optional[Callable[[], None]] = None,
        allow_unset: bool = False,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._choices = list(choices)
        self._allow_unset = allow_unset
        self._on_change = on_change or (lambda: None)
        self._buttons: List[Gtk.ToggleButton] = []
        self._selected: Optional[str] = None
        self._suppress = False

        flow = Gtk.FlowBox(
            max_children_per_line=8,
            selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=4,
            row_spacing=4,
            valign=Gtk.Align.START,
            halign=Gtk.Align.START,
        )
        self.append(flow)

        if allow_unset:
            self._add_button(flow, "", label=tr("choice.unset"))
        for choice in choices:
            self._add_button(flow, choice)

    def _add_button(self, flow: Gtk.FlowBox, value: str, label: Optional[str] = None):
        btn = Gtk.ToggleButton(label=label or value)
        btn.set_group(self._buttons[0] if self._buttons else None)
        btn.connect("toggled", self._on_toggled, value)
        self._buttons.append(btn)
        flow.append(btn)

    def _on_toggled(self, btn: Gtk.ToggleButton, value: str) -> None:
        if self._suppress:
            return
        if not btn.get_active():
            return
        self._selected = value
        # Disattiva gli altri (comportamento "uno solo alla volta"). Il gruppo
        # radio lo farebbe già, ma lo facciamo esplicito per sicurezza.
        for other in self._buttons:
            if other is not btn:
                self._suppress = True
                other.set_active(False)
                self._suppress = False
        self._on_change()

    # -- API valori ----------------------------------------------------------
    def get_value(self) -> str:
        return self._selected or ""

    def set_value(self, value: str) -> None:
        value = str(value or "")
        self._selected = value
        self._suppress = True
        for btn, choice_value in zip(self._buttons, self._value_list()):
            btn.set_active(choice_value == value)
        self._suppress = False

    def _value_list(self) -> List[str]:
        vals = [""] if self._allow_unset else []
        vals.extend(self._choices)
        return vals

    def set_sensitive(self, sensitive: bool) -> None:
        for btn in self._buttons:
            btn.set_sensitive(bool(sensitive))


# ===========================================================================
# Stepper numerico (pulsanti - / + con min e max)
# ===========================================================================
class StepperBox(Gtk.Box):
    """Campo numerico con pulsanti "-" e "+", vincolato tra ``min`` e ``max``.

    Usato per le opzioni numeriche (int e float). Supporta step e decimali.
    """

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
# Riga dichiarativa per un'opzione (checkbox Includi + widget)
# ===========================================================================
class OptionRow(Gtk.Box):
    """Riga completa per un'opzione della tabella.

    Struttura:
        [ ] Includi    <chiave>          <- barra alta
        <widget input costruito per tipo>

    Comportamento:
      * l'input è SEMPRE attivo; modificare il valore abilita "Includi";
      * il checkbox "Includi" controlla solo se l'opzione viene scritta;
      * quando non inclusa la riga è leggermente attenuata (opacity).
    """

    def __init__(
        self,
        spec,
        on_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._on_change = on_change or (lambda _sid: None)
        self.spec = spec
        self._suppress = False

        # Barra alta: checkbox "Includi" + nome opzione (tooltip descrizione)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.include = Gtk.CheckButton(label=tr("widget.include"))
        self.include.set_tooltip_text(tr("widget.include.tooltip").format(key=spec.key))
        title = Gtk.Label(label=spec.key, xalign=0.0, hexpand=True, wrap=True)
        title.set_tooltip_text(spec.description)
        bar.append(self.include)
        bar.append(title)
        self.append(bar)

        # Widget input: costruito per tipo
        self._input = self._build_input(spec)
        self.append(self._input)

        self.include.connect("toggled", self._on_include_toggled)
        self._suppress = True
        self.set_include(False)

    # -- costruzione widget --------------------------------------------------
    def _build_input(self, spec):
        t = spec.type
        if t in ("int", "float"):
            return StepperBox(
                value=float(spec.default or 0),
                min_value=spec.min_value,
                max_value=spec.max_value,
                step=0.1 if t == "float" else 1,
                digits=2 if t == "float" else 0,
                on_change=self._on_value_changed,
            )
        if t == "bool":
            sw = Gtk.Switch(active=bool(spec.default))
            sw.add_css_class("h5")
            sw.set_halign(Gtk.Align.START)
            sw.set_valign(Gtk.Align.CENTER)
            sw.set_hexpand(False)
            sw.connect("notify::active", lambda *_: self._on_value_changed())
            return sw
        if t == "choice":
            return ChoicePicker(
                choices=list(spec.choices or []),
                on_change=self._on_value_changed,
                allow_unset=(spec.default == ""),
            )
        if t == "list":
            return ListEditor(on_change=self._on_value_changed)
        # string / fallback
        entry = Gtk.Entry(text=str(spec.default))
        entry.connect("changed", lambda *_: self._on_value_changed())
        return entry

    # -- segnali --------------------------------------------------------------
    def _on_include_toggled(self, *_):
        if not self._suppress:
            self._set_dimming()
            self._on_change(self.spec.id)

    def _on_value_changed(self, *_):
        if not self._suppress:
            self.include.set_active(True)
            self._set_dimming()
            self._on_change(self.spec.id)

    def _set_dimming(self) -> None:
        opacity = 0.55 if not self.include.get_active() else 1.0
        self._input.set_opacity(opacity)

    # -- API pubblica ----------------------------------------------------------
    def set_include(self, enabled: bool):
        self.include.set_active(bool(enabled))
        self._set_dimming()

    def get_include(self) -> bool:
        return self.include.get_active()

    def set_value(self, value) -> None:
        try:
            if self.spec.type == "bool":
                self._input.set_active(bool(value))
            else:
                self._input.set_value(value)
        except (TypeError, ValueError):
            return
        # Un valore impostato programmaticamente è comunque una modifica:
        # se non siamo in fase di popolamento iniziale, propaga lo stato.
        if not self._suppress:
            self.include.set_active(True)
            self._set_dimming()
            self._on_change(self.spec.id)

    def get_value(self):
        return self._input.get_value()