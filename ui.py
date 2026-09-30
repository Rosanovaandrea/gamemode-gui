"""Interfaccia GTK4/Libadwaita — un unico file, diviso per step.

Struttura del file (per facilitare la navigazione):

  1. CAPITOLO 1 — import, costanti, dialoghi
  2. CAPITOLO 2 — controller di sessione (stato in memoria)
  3. CAPITOLO 3 — widget dichiarativi (una riga per ogni opzione della tabella)
  4. CAPITOLO 4 — STEP 1: Generale ([general])
  5. CAPITOLO 5 — STEP 2: Filtro ([filter])
  6. CAPITOLO 6 — STEP 3: GPU ([gpu]) con banner di avviso
  7. CAPITOLO 7 — STEP 4: Riepilogo + salva + ripristini
  8. CAPITOLO 8 — STEP 5: Riavvio daemon + gruppo gamemode
  9. CAPITOLO 9 — Finestra principale (navigazione tra gli step)
 10. CAPITOLO 10 — Applicazione (entry point Gtk)

Le stringhe visibili passano SEMPRE da core.tr() (i18n via XML), mai hardcodate.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

import core
from core import ConfigManager, OptionSpec, tr


# ===========================================================================
# CAPITOLO 1 — costanti globali e dialoghi
# ===========================================================================

# Meta dati degli step: (titolo, progresso) usati per la navigazione.
STEPS_META = [
    (tr("step.general.title"), "1/5"),
    (tr("step.filter.title"), "2/5"),
    (tr("step.gpu.title"), "3/5"),
    (tr("step.summary.title"), "4/5"),
    (tr("step.restart.title"), "5/5"),
]


def resolve_config_path() -> str:
    """Percorso del file gamemode.ini gestito dalla GUI.

    Default: /etc/gamemode.ini (percorso unico e privilegiato, dove il daemon
    applica anche le ottimizzazioni [gpu]). Sovrascrivibile con la variabile
    GAMEMODE_CONFIG per i test.
    """
    override = os.environ.get("GAMEMODE_CONFIG")
    if override:
        return override
    return "/etc/gamemode.ini"


def _make_dialog(parent, heading: str, body: str, responses: List[str],
                 default: Optional[str] = None) -> Adw.MessageDialog:
    """Crea un Adw.MessageDialog già configurato."""
    dlg = Adw.MessageDialog(transient_for=parent)
    dlg.set_heading(heading)
    dlg.set_body(body)
    for resp in responses:
        dlg.add_response(resp, resp)
    if default:
        dlg.set_default_response(default)
    return dlg


def info_dialog(parent, heading: str, body: str, close: str = tr("dlg.ok")) -> Adw.MessageDialog:
    return _make_dialog(parent, heading, body, [close], default=close)


def confirm_dialog(parent, heading: str, body: str,
                   confirm: str = tr("dlg.confirm")) -> Adw.MessageDialog:
    return _make_dialog(parent, heading, body, [confirm, tr("dlg.cancel")],
                        default=tr("dlg.cancel"))


def error_dialog(parent, heading: str, body: str) -> Adw.MessageDialog:
    dlg = _make_dialog(parent, heading, body, [tr("dlg.retry"), tr("dlg.close")],
                       default=tr("dlg.close"))
    dlg.set_response_appearance(tr("dlg.retry"), Adw.ResponseAppearance.SUGGESTED)
    return dlg


def missing_dialog(parent, heading: str, body: str) -> Adw.MessageDialog:
    """Dialogo per "file non trovato" / ripristino fallito."""
    return info_dialog(parent, heading, body, close=tr("dlg.close"))


def output_dialog(parent, heading: str, output: str, success: bool) -> Adw.MessageDialog:
    """Mostra l'output di un comando (test/riavvio/aggiunta gruppo)."""
    dlg = Adw.MessageDialog(transient_for=parent)
    dlg.set_heading(heading)
    body = tr("dlg.test.ok") if success else tr("dlg.group.failed")
    if not success and not output:
        body = tr("dlg.group.failed")
    dlg.set_body(body)

    scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    scroller.set_size_request(-1, 240)
    view = Gtk.TextView(editable=False, monospace=True,
                        wrap_mode=Gtk.WrapMode.WORD_CHAR)
    buf = view.get_buffer()
    buf.set_text(output or tr("dlg.group.none"))
    scroller.set_child(view)
    dlg.set_extra_child(scroller)

    dlg.add_response(tr("dlg.close"), tr("dlg.close"))
    dlg.set_default_response(tr("dlg.close"))
    return dlg


# ===========================================================================
# CAPITOLO 2 — controller di sessione (stato in memoria)
# ===========================================================================
# Mantiene flag di attivazione + valori correnti. Legge dal file all'avvio e
# al commit scrive sia il file di config sia la sessione JSON.

class SessionController:
    """Stato in memoria: ogni opzione ha un flag "includi" e un valore."""

    def __init__(self) -> None:
        self.activation = core.ActivationManager()
        self.values = {spec.id: spec.default for spec in core.OPTIONS}
        self.on_change: Optional[Callable[[], None]] = None

    def load_from_path(self, config_path: str) -> None:
        """Carica flag/valori dal file attivo (o dai default)."""
        self.values = self.activation.rebuild_from_file(config_path)
        # Se il file non esiste ancora, proviamo a ripartire dalla sessione
        # precedente (le "scelte" salvate al commit).
        if not os.path.isfile(config_path):
            restored = core.load_session(config_path)
            if restored is not None:
                flags, values = restored
                for spec in core.OPTIONS:
                    self.activation.set_flag(spec.id, bool(flags.get(spec.id, False)))
                    if spec.id in values:
                        self.values[spec.id] = _coerce_value(spec, values[spec.id])

    def set_option(self, spec_id: str, value) -> None:
        self.values[spec_id] = value
        self.activation.enable(spec_id)
        if self.on_change:
            self.on_change()

    def set_include(self, spec_id: str, enabled: bool) -> None:
        self.activation.set_flag(spec_id, bool(enabled))
        if self.on_change:
            self.on_change()

    def get_value(self, spec_id: str):
        return self.values.get(spec_id)

    def is_active(self, spec_id: str) -> bool:
        return self.activation.get_flag(spec_id)

    def render(self) -> str:
        flags = {spec.id: self.activation.get_flag(spec.id) for spec in core.OPTIONS}
        return core.render_ini(flags, self.values)


def _coerce_value(spec: OptionSpec, raw):
    """Converte un valore caricato da sessione JSON al tipo della spec."""
    try:
        if spec.type == "int":
            return int(raw)
        if spec.type == "float":
            return float(raw)
        if spec.type == "bool":
            return bool(raw)
        if spec.type == "list":
            return list(raw) if isinstance(raw, list) else [str(raw)]
        if spec.type == "choice" and spec.choices and raw not in spec.choices:
            return spec.default
        return raw
    except (TypeError, ValueError):
        return spec.default


# ===========================================================================
# CAPITOLO 3 — widget dichiarativi (importati da widgets.py, riutilizzabili)
# ===========================================================================
# La costruzione dei widget per ogni tipo di opzione non vive qui ma in
# `widgets.py`: ChoicePicker (radio, niente dropdown), StepperBox (- / +),
# ListEditor e OptionRow (riga completa con checkbox Includi).

from widgets import OptionRow  # noqa: E402



# ===========================================================================
# CAPITOLO 4 — STEP 1: Generale ([general])
# ===========================================================================

class GeneralStep(Gtk.Box):
    """Form con tutte le opzioni della sezione [general]."""

    def __init__(self, controller: SessionController) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self.rows: List[OptionRow] = []
        self.append(_header(tr("step.general.title"), tr("step.general.subtitle")))
        self.append(_option_page(controller, "general", self.rows))


# ===========================================================================
# CAPITOLO 5 — STEP 2: Filtro ([filter])
# ===========================================================================

class FilterStep(Gtk.Box):
    """Step con whitelist e blacklist dei programmi."""

    def __init__(self, controller: SessionController) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self.rows: List[OptionRow] = []
        self.append(_header(tr("step.filter.title"), tr("step.filter.subtitle")))
        self.append(_option_page(controller, "filter", self.rows))


# ===========================================================================
# CAPITOLO 6 — STEP 3: GPU ([gpu]) con banner di avviso
# ===========================================================================

class GpuStep(Gtk.Box):
    """Step con le ottimizzazioni hardware (NVIDIA/AMD) + avviso sicurezza."""

    def __init__(self, controller: SessionController) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self.rows: List[OptionRow] = []

        banner = Adw.Banner(title=tr("gpu.banner"))
        banner.add_css_class("error")
        self.append(banner)

        self.append(_header(tr("step.gpu.title"), tr("step.gpu.subtitle")))
        self.append(_option_page(controller, "gpu", self.rows))


# ===========================================================================
# CAPITOLO 7 — STEP 4: Riepilogo + salva + ripristini
# ===========================================================================

class SummaryStep(Gtk.Box):
    """Anteprima del file + pulsanti Salva / ripristinare backup / originale."""

    def __init__(self, controller: SessionController, actions) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self.actions = actions

        self.append(_header(tr("step.summary.title"), tr("step.summary.subtitle")))

        scroller = Gtk.ScrolledWindow(vexpand=True)
        view = Gtk.TextView(editable=False, monospace=True,
                            wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self._buf = view.get_buffer()
        scroller.set_child(view)
        self.append(scroller)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save = Gtk.Button(label=tr("btn.save"))
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *_: actions.do_save())
        rest_bak = Gtk.Button(label=tr("btn.restore_backup"))
        rest_bak.connect("clicked", lambda *_: actions.do_restore_backup())
        rest_orig = Gtk.Button(label=tr("btn.restore_orig"))
        rest_orig.connect("clicked", lambda *_: actions.do_restore_orig())
        btn_row.append(save)
        btn_row.append(rest_bak)
        btn_row.append(rest_orig)
        self.append(btn_row)

        self.refresh()

    def refresh(self) -> None:
        self._buf.set_text(self.controller.render())


# ===========================================================================
# CAPITOLO 8 — STEP 5: Riavvio daemon + gruppo gamemode
# ===========================================================================

class RestartStep(Gtk.Box):
    """Schermata finale: conferma salvataggio + riavvio/aggiunta gruppo."""

    def __init__(self, actions) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.actions = actions
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)

        icon = Gtk.Image(icon_name="emblem-ok-symbolic", pixel_size=48)
        self.append(icon)
        self.append(Gtk.Label(label=tr("step.restart.title"),
                              css_classes=["title-1"]))
        desc = Gtk.Label(label=tr("step.restart.desc"),
                         wrap=True, justify=Gtk.Justification.CENTER)
        self.append(desc)

        self.group_status = Gtk.Label(label="", css_classes=["dim-label"], wrap=True)
        self.group_status.set_halign(Gtk.Align.CENTER)
        self.append(self.group_status)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        restart = Gtk.Button(label=tr("btn.restart_daemon"))
        restart.add_css_class("suggested-action")
        restart.connect("clicked", lambda *_: actions.do_restart_daemon())
        close = Gtk.Button(label=tr("nav.close"))
        close.connect("clicked", lambda *_: actions.close())
        self.add_group_btn = Gtk.Button(label=tr("btn.add_group"))
        btn_row.append(restart)
        btn_row.append(close)
        self.append(btn_row)
        self.append(self.add_group_btn)

        self.add_group_btn.connect("clicked", lambda *_: actions.do_add_group(self.refresh_group))
        self.refresh_group()

    def refresh_group(self) -> None:
        """Aggiorna lo stato del gruppo gamemode."""
        if not core.group_exists():
            self.add_group_btn.set_sensitive(False)
            self.group_status.set_text(tr("step.restart.group_missing"))
        elif core.user_in_group():
            self.add_group_btn.set_sensitive(False)
            self.group_status.set_text(tr("step.restart.group_in"))
        else:
            self.add_group_btn.set_sensitive(True)
            self.group_status.set_text(tr("step.restart.group_out"))


# ===========================================================================
# Helper condivisi tra gli step (non esposti all'esterno)
# ===========================================================================

def _header(title: str, subtitle: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.append(Gtk.Label(label=title, xalign=0.0, css_classes=["title-2"]))
    box.append(Gtk.Label(label=subtitle, xalign=0.0,
                         css_classes=["dim-label"], wrap=True))
    return box


def _option_page(controller: SessionController, section: str,
                 rows: List[OptionRow]) -> Gtk.Widget:
    """Costruisce la lista scorrevole di righe per una sezione."""
    scroller = Gtk.ScrolledWindow(vexpand=True)
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    listbox.add_css_class("boxed-list")

    for spec in core.options_for_section(section):
        row = OptionRow(spec)
        # popola dallo stato caricato, sopprimendo i segnali
        row._suppress = True
        row.set_value(controller.get_value(spec.id))
        row.set_include(controller.is_active(spec.id))
        row._suppress = False

        # aggancia dopo la creazione per catturare la row corretta
        row._on_change = lambda spec_id, _r=row: _apply_row_change(
            controller, _r, spec_id)
        rows.append(row)
        listbox.append(row)

    scroller.set_child(listbox)
    return scroller


def _apply_row_change(controller: SessionController, row: OptionRow,
                      spec_id: str) -> None:
    """Propaga lo stato di una riga (includi + valore) al controller."""
    controller.set_include(spec_id, row.get_include())
    if row.get_include():
        controller.set_option(spec_id, row.get_value())


# ===========================================================================
# CAPITOLO 9 — Finestra principale (navigazione tra gli step)
# ===========================================================================

class GameModeWindow(Adw.ApplicationWindow):
    """Finestra principale: header, stack degli step, footer di navigazione."""

    def __init__(self, *args, **kwargs) -> None:
        application = kwargs.pop("application", None) or (args[0] if args else None)
        super().__init__(application=application, title=tr("window.title"), **kwargs)
        self.set_default_size(760, 640)

        self.config_path = resolve_config_path()
        self.cm = ConfigManager(self.config_path)
        self.controller = SessionController()
        self.controller.on_change = self._mark_dirty
        self._dirty = False
        self._saved = False

        self._init_data()
        self._build_ui()

    # -- dati di sessione -----------------------------------------------------
    def _init_data(self) -> None:
        # Nota: il file .orig (stato "vergine") NON viene creato qui: viene
        # creato automaticamente al primo commit (sia locale sia privilegiato),
        # evitando una richiesta di password root all'avvio dell'app.
        self.controller.load_from_path(self.config_path)

    # -- costruzione UI ---------------------------------------------------------
    def _build_ui(self) -> None:
        self.set_title(tr("window.title"))

        toolbar = Adw.ToolbarView()
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(toolbar)
        self.set_content(self.toast_overlay)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        cancel = Gtk.Button(label=tr("header.cancel"))
        cancel.set_tooltip_text(tr("dlg.unsaved.title"))
        cancel.connect("clicked", lambda *_: self.close())
        test_btn = Gtk.Button(label=tr("header.test"))
        test_btn.set_tooltip_text(tr("header.test.tooltip"))
        test_btn.connect("clicked", lambda *_: self._run_tests())
        help_btn = Gtk.Button(icon_name="help-about-symbolic")
        help_btn.set_tooltip_text(tr("header.help.tooltip"))
        help_btn.connect("clicked", lambda *_: self._show_help())
        header.pack_start(cancel)
        header.pack_end(help_btn)
        header.pack_end(test_btn)

        # Centrale: etichetta di avanzamento (1/5 .. 5/5)
        self.progress_label = Gtk.Label(label=STEPS_META[0][1],
                                        css_classes=["dim-label"])
        center = Gtk.Box()
        center.set_halign(Gtk.Align.CENTER)
        center.append(self.progress_label)
        header.set_title_widget(center)

        # Stack degli step (ViewStack + transizione)
        self.stack = Adw.ViewStack()
        if hasattr(self.stack, "set_transition_type"):
            self.stack.set_transition_type(Adw.ViewStackTransitionType.SLIDE_LEFT_RIGHT)

        self.general_step = GeneralStep(self.controller)
        self.filter_step = FilterStep(self.controller)
        self.gpu_step = GpuStep(self.controller)
        self.summary_step = SummaryStep(self.controller, self)
        self.restart_step = RestartStep(self)

        pages = [self.general_step, self.filter_step, self.gpu_step,
                 self.summary_step, self.restart_step]
        for i, page in enumerate(pages):
            self.stack.add_named(page, f"step-{i}")

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.append(self.stack)

        # Footer: Indietro / Avanti
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_top(12)
        footer.set_margin_bottom(12)
        footer.set_margin_start(16)
        footer.set_margin_end(16)
        self.go_back = Gtk.Button(label=tr("nav.back"))
        self.go_next = Gtk.Button(label=tr("nav.next"))
        self.go_next.add_css_class("suggested-action")
        footer.append(self.go_back)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)
        footer.append(self.go_next)
        wrapper.append(footer)

        toolbar.set_content(wrapper)

        self._current = 0
        self.go_back.connect("clicked", lambda *_: self._navigate(-1))
        self.go_next.connect("clicked", lambda *_: self._navigate(+1))
        self.connect("close-request", self._on_close_request)
        self._update_controls()

    # -- navigazione -------------------------------------------------------------
    def _navigate(self, delta: int) -> None:
        target = self._current + delta
        if not (0 <= target < len(STEPS_META)):
            return
        self._current = target
        self.stack.set_visible_child_name(f"step-{target}")
        if target == 3:
            self.summary_step.refresh()
        self._update_controls()

    def _update_controls(self) -> None:
        self.progress_label.set_text(STEPS_META[self._current][1])
        self.go_back.set_sensitive(self._current > 0)
        self.go_next.set_sensitive(self._current < len(STEPS_META) - 1)
        if self._current >= 3:
            self.go_next.set_label(tr("nav.close"))
        else:
            self.go_next.set_label(tr("nav.next"))

    # -- dirty tracking -------------------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True

    def _on_close_request(self, *_):
        if self._saved:
            return False
        if self._dirty:
            dlg = confirm_dialog(self, tr("dlg.unsaved.title"),
                                 tr("dlg.unsaved.body"),
                                 confirm=tr("dlg.unsaved.exit"))
            dlg.present()
            dlg.connect("response", self._closed_confirmed)
            return True
        return False

    def _closed_confirmed(self, dlg, response: str) -> None:
        dlg.close()
        if response == tr("dlg.unsaved.exit"):
            self._saved = True
            self.close()

    # -- azioni condivise -----------------------------------------------------------
    def do_save(self) -> None:
        """Salva il file attivo (commit atomico) + sessione JSON."""
        try:
            content = self.controller.render()
        except Exception as exc:
            self._run_dialog(error_dialog(self, tr("dlg.render_error.title"), str(exc)))
            return

        try:
            self.cm.save(content)
        except Exception as exc:
            body = tr("dlg.save_error.body").format(error=exc)
            self._run_dialog(error_dialog(self, tr("dlg.save_error.title"), body))
            return

        # Persistenza dello stato delle scelte (le "indici" delle opzioni)
        core.save_session(self.config_path, self.controller.activation.take_snapshot(),
                          self.controller.values)

        # Ricarica il file appena scritto per sincronizzare i flag
        self.controller.load_from_path(self.config_path)
        self.summary_step.refresh()
        self._dirty = False
        self._saved = True
        self._navigate(1)  # -> step 5
        self._show_toast(tr("dlg.save_ok"))

    def do_restore_backup(self) -> None:
        dlg = confirm_dialog(self, tr("dlg.restore_bak.title"),
                             tr("dlg.restore_bak.body"), confirm=tr("btn.restore_backup"))
        dlg.present()
        dlg.connect("response", self._restore_backup_response)

    def _restore_backup_response(self, dlg, response: str) -> None:
        dlg.close()
        if response != tr("btn.restore_backup"):
            return
        if self.cm.rollback_from_backup():
            self.controller.load_from_path(self.config_path)
            self.summary_step.refresh()
            self._mark_dirty()
            self._show_toast(tr("dlg.restore_bak.ok"))
        else:
            self._run_dialog(missing_dialog(self, tr("dlg.restore_bak.title"),
                                            tr("dlg.restore_bak.none")))

    def do_restore_orig(self) -> None:
        dlg = confirm_dialog(self, tr("dlg.restore_orig.title"),
                             tr("dlg.restore_orig.body"), confirm=tr("btn.restore_orig"))
        dlg.present()
        dlg.connect("response", self._restore_orig_response)

    def _restore_orig_response(self, dlg, response: str) -> None:
        dlg.close()
        if response != tr("btn.restore_orig"):
            return
        if self.cm.restore_from_orig():
            self.controller.load_from_path(self.config_path)
            self.summary_step.refresh()
            self._mark_dirty()
            self._show_toast(tr("dlg.restore_orig.ok"))
        else:
            self._run_dialog(missing_dialog(self, tr("dlg.restore_orig.title"),
                                            tr("dlg.restore_orig.none")))

    def do_add_group(self, on_done=None) -> None:
        res = core.add_user_to_group()
        dlg = output_dialog(self, tr("dlg.group.title"), res.output, res.success)
        dlg.present()
        dlg.connect("response", lambda *_a: on_done() if on_done else None)
        if res.success:
            dlg.connect("response", lambda *_a: self._run_dialog(
                info_dialog(self, tr("dlg.logout.title"), tr("dlg.logout.body"))))

    def do_restart_daemon(self) -> None:
        res = core.restart_daemon()
        dlg = output_dialog(self, tr("dlg.restart.title"), res.output, res.success)
        dlg.present()

    def _run_tests(self) -> None:
        """§5.2: test del daemon + versione mostrati in un dialogo."""
        res_test = core.test_daemon()
        res_ver = core.daemon_version()
        lines = [
            "---- gamemoded -t ----",
            res_test.output or ("OK" if res_test.success else tr("dlg.group.failed")),
            "",
            "---- gamemoderun --version ----",
            res_ver.output or ("OK" if res_ver.success else tr("dlg.group.failed")),
        ]
        ok = res_test.success and res_ver.success
        self._run_dialog(output_dialog(self, tr("dlg.test.title"), "\n".join(lines), ok))

    def _show_help(self) -> None:
        self._run_dialog(info_dialog(self, tr("dlg.help.title"), tr("dlg.help.body")))

    def _run_dialog(self, dlg: Adw.MessageDialog) -> None:
        dlg.present()

    def _show_toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=message))


# ===========================================================================
# CAPITOLO 10 — Applicazione (entry point Gtk)
# ===========================================================================
# La logica viene importata da ui senza eseguire il main loop al import:
# solo la funzione main() lo avvia.

class GameModeApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.gamemodegui.GameModeGui",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._window: Optional[GameModeWindow] = None

    def do_activate(self) -> None:
        if self._window is None:
            self._window = GameModeWindow(application=self)
        self._window.present()


def main() -> int:
    """Entry point per lanciare l'applicazione."""
    app = GameModeApplication()
    return app.run(sys.argv)