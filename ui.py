"""Interfaccia GTK4/Libadwaita — un unico file, con schede generate dai dati.

Struttura del file (per facilitare la navigazione):

  1. CAPITOLO 1 — import, costanti, dialoghi, stile console
  2. CAPITOLO 2 — controller di sessione (stato in memoria)
  3. CAPITOLO 3 — schede delle opzioni (generate da options.json)
  4. CAPITOLO 4 — scheda Riepilogo (anteprima + salva + ripristini)
  5. CAPITOLO 5 — scheda Daemon (console, riavvio, test, gruppo gamemode)
  6. CAPITOLO 6 — helper condivisi tra le schede
  7. CAPITOLO 7 — finestra principale (ViewStack + ViewSwitcher a schede)
  8. CAPITOLO 8 — applicazione (entry point Gtk)

Le stringhe visibili passano SEMPRE da core.tr() (i18n via XML), mai hardcodate.
Le schede e le opzioni derivano da `options.json`: aggiungere una voce lì basta.
"""

from __future__ import annotations

import getpass
import os
import sys
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

import core
from core import Category, ConfigManager, OptionSpec, tr


# ===========================================================================
# CAPITOLO 1 — costanti globali, dialoghi, stile console
# ===========================================================================

# Schede visibili: le categorie (da options.json) + Riepilogo e Daemon.
TABS_META = [(cat.id, tr(cat.tab_id)) for cat in core.CATEGORIES] + [
    ("summary", tr("tab.summary")),
    ("daemon", tr("tab.daemon")),
]


def resolve_config_path() -> str:
    """Percorso del file gamemode.ini gestito dalla GUI.

    Default: /etc/gamemode.ini (percorso unico e privilegiato). Sovrascrivibile
    con la variabile GAMEMODE_CONFIG per i test.
    """
    override = os.environ.get("GAMEMODE_CONFIG")
    if override:
        return override
    return "/etc/gamemode.ini"


def _make_dialog(parent, heading: str, body: str, responses: List[str],
                 default: Optional[str] = None) -> Adw.MessageDialog:
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


# Stile della "console simulata" della scheda Daemon (aspetto da terminale).
_CONSOLE_CSS = b"""
.console, .console text {
  background-color: #16181d;
  color: #e6e6e6;
  font-family: monospace;
}
"""


def install_console_css() -> None:
    """Registra lo stile della console (best effort, mai fatale)."""
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CONSOLE_CSS)
        display = Gtk.Widget.get_default_display()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    except Exception:
        pass


# ===========================================================================
# CAPITOLO 2 — controller di sessione (stato in memoria)
# ===========================================================================

class SessionController:
    """Stato in memoria: il valore corrente di ogni opzione.

    I valori "effettivi" sono il risultato del merge tra il file installato
    dal pacchetto (base) e l'override in /etc, come fa il daemon.
    """

    def __init__(self) -> None:
        self.values = {spec.id: spec.default for spec in core.OPTIONS}
        self.base_path: Optional[str] = None
        self.base_comments: dict = {}
        self.on_change: Optional[Callable[[], None]] = None

    def load_from_path(self, override_path: str, base_path: Optional[str] = None) -> None:
        """Carica i valori effettivi (base installata + override)."""
        self.base_path = base_path if base_path and os.path.isfile(base_path) else None
        self.base_comments = core.load_base_comments(self.base_path)
        self.values = core.load_effective_values(self.base_path, override_path)
        # Se non esiste né l'override né la base, proviamo la sessione salvata.
        if not os.path.isfile(override_path) and self.base_path is None:
            restored = core.load_session(override_path)
            if restored is not None:
                for spec in core.OPTIONS:
                    if spec.id in restored:
                        self.values[spec.id] = _coerce_value(spec, restored[spec.id])

    def set_option(self, spec_id: str, value) -> None:
        self.values[spec_id] = value
        if self.on_change:
            self.on_change()

    def get_value(self, spec_id: str):
        return self.values.get(spec_id)

    def render(self) -> str:
        return core.render_ini(self.values, self.base_comments)


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
# CAPITOLO 3 — schede delle opzioni (generate dalle categorie)
# ===========================================================================

from widgets import OptionRow  # noqa: E402


class OptionTab(Gtk.Box):
    """Scheda con tutte le opzioni di una categoria + pulsante Salva."""

    def __init__(self, category: Category, controller: SessionController, actions) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.category = category
        self.controller = controller
        self.actions = actions
        self.rows: List[OptionRow] = []

        self.append(_header(tr(category.title_id), tr(category.subtitle_id)))
        self.append(_build_option_list(controller, category, self.rows))
        self.append(self._save_bar())
        if category.banner_id:
            banner = Adw.Banner(title=tr(category.banner_id))
            banner.add_css_class("error")
            self.prepend(banner)
        self.refresh_gating()

    def _save_bar(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.set_halign(Gtk.Align.END)
        save = Gtk.Button(label=tr("btn.save"))
        save.add_css_class("suggested-action")
        save.set_tooltip_text(tr("btn.save.tooltip"))
        save.connect("clicked", lambda *_: self.actions.do_save())
        bar.append(save)
        return bar

    def refresh(self) -> None:
        """Riallinea tutte le righe allo stato del controller."""
        for row in self.rows:
            _populate_row(row, self.controller)
        self.refresh_gating()

    def refresh_gating(self) -> None:
        """Abilita/disabilita le opzioni in base alle loro dipendenze."""
        values = self.controller.values
        for row in self.rows:
            dep = getattr(row.spec, "depends_on", None)
            if dep:
                row.set_enabled(core.dependency_met(row.spec, values))


# ===========================================================================
# CAPITOLO 4 — scheda Riepilogo (anteprima + salva + ripristini)
# ===========================================================================

class SummaryTab(Gtk.Box):
    """Anteprima del file + pulsanti Salva / ripristini."""

    def __init__(self, controller: SessionController, actions,
                 config_path: str = "", base_path: Optional[str] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self.actions = actions

        self.append(_header(tr("step.summary.title"), tr("step.summary.subtitle")))
        if config_path:
            self.append(Gtk.Label(label=tr("summary.path").format(path=config_path),
                                  xalign=0.0, wrap=True, css_classes=["dim-label"]))
        if base_path:
            self.append(Gtk.Label(label=tr("summary.base").format(path=base_path),
                                  xalign=0.0, wrap=True, css_classes=["dim-label"]))

        scroller = Gtk.ScrolledWindow(vexpand=True)
        view = Gtk.TextView(editable=False, monospace=True,
                            wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self._buf = view.get_buffer()
        scroller.set_child(view)
        self.append(scroller)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        save = Gtk.Button(label=tr("btn.save"))
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *_: actions.do_save())
        rest_bak = Gtk.Button(label=tr("btn.restore_backup"))
        rest_bak.connect("clicked", lambda *_: actions.do_restore_backup())
        rest_orig = Gtk.Button(label=tr("btn.restore_orig"))
        rest_orig.connect("clicked", lambda *_: actions.do_restore_orig())
        btn_row.append(rest_bak)
        btn_row.append(rest_orig)
        btn_row.append(save)
        self.append(btn_row)

        self.refresh()

    def refresh(self) -> None:
        self._buf.set_text(self.controller.render())


# ===========================================================================
# CAPITOLO 5 — scheda Daemon (console, riavvio, test, gruppo gamemode)
# ===========================================================================

class DaemonTab(Gtk.Box):
    """Gestione del daemon: riavvio, test, gruppo gamemode e console simulata."""

    def __init__(self, actions) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.actions = actions

        self.append(_header(tr("tab.daemon.title"), tr("tab.daemon.subtitle")))

        # Riquadro azioni sul daemon.
        actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        actions_box.add_css_class("card")
        actions_box.set_margin_top(4)
        actions_box.set_margin_bottom(4)
        actions_box.set_margin_start(4)
        actions_box.set_margin_end(4)

        restart = Gtk.Button(label=tr("btn.restart_daemon"))
        restart.add_css_class("suggested-action")
        restart.set_halign(Gtk.Align.START)
        restart.connect("clicked", lambda *_: actions.do_restart_daemon())
        test = Gtk.Button(label=tr("btn.test_daemon"))
        test.set_halign(Gtk.Align.START)
        test.connect("clicked", lambda *_: actions.run_tests())
        actions_box.append(restart)
        actions_box.append(test)
        self.append(actions_box)

        # Riquadro gruppo gamemode.
        group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        group_box.add_css_class("card")
        group_box.set_margin_top(4)
        group_box.set_margin_bottom(4)
        group_box.set_margin_start(4)
        group_box.set_margin_end(4)
        group_box.append(Gtk.Label(label=tr("daemon.group.title"), xalign=0.0,
                                   css_classes=["heading"]))
        self.group_status = Gtk.Label(label="", xalign=0.0, wrap=True,
                                      css_classes=["dim-label"])
        group_box.append(self.group_status)
        self.add_group_btn = Gtk.Button(label=tr("btn.add_group"))
        self.add_group_btn.set_halign(Gtk.Align.START)
        self.add_group_btn.connect(
            "clicked", lambda *_: actions.do_add_group(self.refresh_group))
        group_box.append(self.add_group_btn)
        self.append(group_box)

        # Console simulata: sempre visibile, mostra i comandi e il loro output
        # grezzo (senza alcun verdetto di successo/errore).
        console_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        console_header.append(Gtk.Label(label=tr("daemon.console.title"), xalign=0.0,
                                        hexpand=True, css_classes=["heading"]))
        clear = Gtk.Button(label=tr("daemon.console.clear"))
        clear.add_css_class("flat")
        clear.connect("clicked", lambda *_: self.clear_console())
        console_header.append(clear)
        self.append(console_header)

        self._console_view = Gtk.TextView(editable=False, monospace=True,
                                          wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                          cursor_visible=False)
        self._console_view.add_css_class("console")
        self._console_buf = self._console_view.get_buffer()
        console_scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        console_scroller.set_child(self._console_view)
        self.append(console_scroller)

        self.refresh_group()

    # -- console simulata -----------------------------------------------------
    def clear_console(self) -> None:
        self._console_buf.set_text("")

    def append_console(self, text: str) -> None:
        """Aggiunge testo alla console e scorre in fondo."""
        if text is None:
            return
        end = self._console_buf.get_end_iter()
        self._console_buf.insert(end, text)
        if not text.endswith("\n"):
            self._console_buf.insert(self._console_buf.get_end_iter(), "\n")
        self._console_view.scroll_to_iter(
            self._console_buf.get_end_iter(), 0.0, False, 0.0, 0.0)

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
# CAPITOLO 6 — helper condivisi tra le schede
# ===========================================================================

def _header(title: str, subtitle: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.append(Gtk.Label(label=title, xalign=0.0, css_classes=["title-2"]))
    box.append(Gtk.Label(label=subtitle, xalign=0.0,
                         css_classes=["dim-label"], wrap=True))
    return box


def _build_option_list(controller: SessionController, category: Category,
                       rows: List[OptionRow]) -> Gtk.Widget:
    """Costruisce la lista scorrevole di righe per una categoria."""
    scroller = Gtk.ScrolledWindow(vexpand=True)
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    listbox.add_css_class("boxed-list")

    for spec in category.options:
        row = OptionRow(spec)
        _populate_row(row, controller)
        row._on_change = lambda spec_id, _r=row: _apply_row_change(
            controller, _r, spec_id)
        rows.append(row)
        listbox.append(row)

    scroller.set_child(listbox)
    return scroller


def _populate_row(row: OptionRow, controller: SessionController) -> None:
    """Sincronizza una riga con lo stato corrente, senza propagare eventi."""
    row._suppress = True
    row.set_value(controller.get_value(row.spec.id))
    row._suppress = False


def _apply_row_change(controller: SessionController, row: OptionRow,
                      spec_id: str) -> None:
    controller.set_option(spec_id, row.get_value())


# ===========================================================================
# CAPITOLO 7 — Finestra principale (navigazione a schede)
# ===========================================================================

class GameModeWindow(Adw.ApplicationWindow):
    """Finestra principale: header con selettore a schede + stack delle schede."""

    def __init__(self, *args, **kwargs) -> None:
        application = kwargs.pop("application", None) or (args[0] if args else None)
        super().__init__(application=application, title=tr("window.title"), **kwargs)
        self.set_default_size(1180, 820)

        self.config_path = resolve_config_path()
        # Base = gamemode.ini installato dal pacchetto (variabile per distro).
        self.base_path = core.resolve_base_path()
        self.base_content = self._read_text(self.base_path)
        self.cm = ConfigManager(self.config_path, orig_seed=self.base_content)
        self.controller = SessionController()
        self.controller.on_change = self._mark_dirty
        self._dirty = False

        self._init_data()
        self._build_ui()

    @staticmethod
    def _read_text(path: Optional[str]) -> str:
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                pass
        return ""

    def _init_data(self) -> None:
        self.controller.load_from_path(self.config_path, self.base_path)

    # -- costruzione UI ---------------------------------------------------------
    def _build_ui(self) -> None:
        self.set_title(tr("window.title"))
        install_console_css()

        toolbar = Adw.ToolbarView()
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(toolbar)
        self.set_content(self.toast_overlay)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        help_btn = Gtk.Button(icon_name="help-about-symbolic")
        help_btn.set_tooltip_text(tr("header.help.tooltip"))
        help_btn.connect("clicked", lambda *_: self._show_help())
        header.pack_end(help_btn)

        # Stack delle schede.
        self.stack = Adw.ViewStack()
        if hasattr(self.stack, "set_transition_type"):
            self.stack.set_transition_type(
                Adw.ViewStackTransitionType.SLIDE_LEFT_RIGHT)

        # Schede delle opzioni: una per categoria definita in options.json.
        self.option_tabs = {}
        pages = {}
        for cat in core.CATEGORIES:
            tab = OptionTab(cat, self.controller, self)
            self.option_tabs[cat.id] = tab
            setattr(self, f"{cat.id}_tab", tab)  # es. general_tab, gpu_tab
            pages[cat.id] = tab

        self.summary_tab = SummaryTab(self.controller, self, self.config_path,
                                      self.base_path)
        self.daemon_tab = DaemonTab(self)
        pages["summary"] = self.summary_tab
        pages["daemon"] = self.daemon_tab

        for name, title in TABS_META:
            self.stack.add_titled(pages[name], name, title)

        switcher = Adw.ViewSwitcher(stack=self.stack)
        if hasattr(Adw, "ViewSwitcherPolicy"):
            switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Margini attorno all'area di contenuto (padding generale della finestra).
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_margin_top(12)
        wrapper.set_margin_bottom(12)
        wrapper.set_margin_start(16)
        wrapper.set_margin_end(16)
        wrapper.append(self.stack)
        toolbar.set_content(wrapper)
        self.connect("close-request", self._on_close_request)

    # -- dirty tracking -------------------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True
        self._refresh_gating()

    def _refresh_gating(self) -> None:
        for tab in getattr(self, "option_tabs", {}).values():
            tab.refresh_gating()

    def _on_close_request(self, *_):
        if not self._dirty:
            return False
        dlg = confirm_dialog(self, tr("dlg.unsaved.title"),
                             tr("dlg.unsaved.body"),
                             confirm=tr("dlg.unsaved.exit"))
        dlg.present()
        dlg.connect("response", self._closed_confirmed)
        return True

    def _closed_confirmed(self, dlg, response: str) -> None:
        dlg.close()
        if response == tr("dlg.unsaved.exit"):
            self._dirty = False
            self.close()

    # -- azioni condivise -----------------------------------------------------------
    def _refresh_all(self) -> None:
        for tab in self.option_tabs.values():
            tab.refresh()
        self.summary_tab.refresh()

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

        core.save_session(self.config_path, self.controller.values)
        self.controller.load_from_path(self.config_path, self.base_path)
        self._refresh_all()
        self._dirty = False
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
            self.controller.load_from_path(self.config_path, self.base_path)
            self._refresh_all()
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
            self.controller.load_from_path(self.config_path, self.base_path)
            self._refresh_all()
            self._mark_dirty()
            self._show_toast(tr("dlg.restore_orig.ok"))
        else:
            self._run_dialog(missing_dialog(self, tr("dlg.restore_orig.title"),
                                            tr("dlg.restore_orig.none")))

    def do_add_group(self, on_done=None) -> None:
        user = getpass.getuser()
        res = core.add_user_to_group()
        console = self.daemon_tab
        console.append_console(tr("daemon.console.cmd").format(
            cmd=f"usermod -aG gamemode {user}"))
        console.append_console(res.output)
        if res.success:
            console.append_console(tr("dlg.logout.body"))
        if on_done:
            on_done()

    def do_restart_daemon(self) -> None:
        res = core.restart_daemon()
        console = self.daemon_tab
        console.append_console(tr("daemon.console.cmd").format(
            cmd="systemctl --user restart gamemoded"))
        console.append_console(res.output)

    def run_tests(self) -> None:
        """Esegue i comandi di test del daemon e ne mostra l'output in console."""
        console = self.daemon_tab
        res_test = core.test_daemon()
        console.append_console(tr("daemon.console.cmd").format(cmd="gamemoded -t"))
        console.append_console(res_test.output)
        res_ver = core.daemon_version()
        console.append_console(tr("daemon.console.cmd").format(
            cmd="gamemoderun --version"))
        console.append_console(res_ver.output)

    def _show_help(self) -> None:
        self._run_dialog(info_dialog(self, tr("dlg.help.title"), tr("dlg.help.body")))

    def _run_dialog(self, dlg: Adw.MessageDialog) -> None:
        dlg.present()

    def _show_toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=message))


# ===========================================================================
# CAPITOLO 8 — Applicazione (entry point Gtk)
# ===========================================================================

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
