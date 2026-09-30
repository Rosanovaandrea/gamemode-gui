"""Main window: navigation between the five configuration steps."""

from __future__ import annotations

import os

from gi.repository import Adw, Gtk

from core import gamemode_utils as gm
from core.backup_manager import BackupManager
from core.config_manager import ConfigManager
from ui import dialogs, steps
from ui.controller import SessionController

STEPS_META = [
    ("Generale", "1/5"),
    ("Filtro", "2/5"),
    ("GPU", "3/5"),
    ("Riepilogo", "4/5"),
    ("Riavvio", "5/5"),
]


def resolve_config_path() -> str:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "gamemode.ini")
    home = os.environ.get("HOME", os.path.expanduser("~"))
    return os.path.join(home, ".config", "gamemode.ini")


class GameModeWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs) -> None:
        application = kwargs.pop("application", None) or (args[0] if args else None)
        super().__init__(application=application, title="GameMode GUI", **kwargs)
        self.set_default_size(720, 620)

        self.config_path = resolve_config_path()
        self.cm = ConfigManager(self.config_path)
        self.bm = BackupManager(self.cm)
        self.controller = SessionController()
        self.controller.on_change = self._mark_dirty
        self._dirty = False
        self._saved = False

        self._init_data()
        self._build_ui()

    # -- session data -----------------------------------------------------
    def _init_data(self) -> None:
        existing = ""
        if os.path.isfile(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as fh:
                existing = fh.read()
        # .orig is created only once, never modified.
        self.bm.ensure_orig_from_existing_or_default(existing)
        self.controller.load(self.config_path)

    # -- UI construction ---------------------------------------------------
    def _build_ui(self) -> None:
        self.content = Adw.ToolbarView()
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_margin_top(1)
        self.toast_overlay.set_child(self.content)
        self.set_content(self.toast_overlay)

        # Header bar
        header = Adw.HeaderBar()
        self.content.add_top_bar(header)

        cancel = Gtk.Button(label="Annulla")
        cancel.connect("clicked", lambda *_: self.close())
        test_btn = Gtk.Button(label="Test")
        test_btn.set_tooltip_text("Esegui i test del daemon e della versione")
        test_btn.connect("clicked", lambda *_: self._run_tests())
        help_btn = Gtk.Button(icon_name="help-about-symbolic")
        help_btn.set_tooltip_text("Aiuto")
        help_btn.connect("clicked", lambda *_: self._show_help())
        header.pack_start(cancel)
        header.pack_end(help_btn)
        header.pack_end(test_btn)

        # Body: the step stack
        self.stack = Adw.ViewStack()
        if hasattr(self.stack, "set_transition_type"):
            self.stack.set_transition_type(Adw.ViewStackTransitionType.SLIDE_LEFT_RIGHT)

        self._general_page = steps.build_general_step(self.controller)
        self._filter_page = steps.build_filter_step(self.controller)
        self._gpu_page = steps.build_gpu_step(self.controller)
        self._summary_page = steps.build_summary_step(self.controller, self)
        self._restart_page = steps.build_restart_step(self.controller, self)

        for i, (title, _tag) in enumerate(STEPS_META):
            page = [self._general_page, self._filter_page, self._gpu_page,
                    self._summary_page, self._restart_page][i]
            self.stack.add_named(page, f"step-{i}")

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header_resp = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.progress_label = Gtk.Label(label=STEPS_META[0][1], css_classes=["dim-label"])
        header_resp.append(self.progress_label)
        # center
        center = Gtk.Box()
        center.set_halign(Gtk.Align.CENTER)
        center.append(header_resp)
        header.set_title_widget(center)

        wrapper.append(self.stack)

        self.content.set_content(wrapper)

        # Footer
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_top(12)
        footer.set_margin_bottom(12)
        footer.set_margin_start(16)
        footer.set_margin_end(16)
        go_back = Gtk.Button(label="Indietro")
        go_next = Gtk.Button(label="Avanti")
        go_next.add_css_class("suggested-action")
        footer.append(go_back)
        footer.append(gtk_spacer())
        footer.append(go_next)
        wrapper.append(footer)

        self._go_back = go_back
        self._go_next = go_next
        self._current = 0
        go_back.connect("clicked", lambda *_: self._navigate(-1))
        go_next.connect("clicked", lambda *_: self._navigate(+1))

        self._update_controls()

        # Close confirmation for unsaved changes
        self.connect("close-request", self._on_close_request)

    def _run_tests(self) -> None:
        """§5.2: run daemon test + version checks and show output."""
        res_test = gm.test_daemon()
        res_ver = gm.daemon_version()

        lines = []
        lines.append("---- gamemoded -t ----")
        lines.append(res_test.output or ("OK" if res_test.success else "errore"))
        lines.append("")
        lines.append("---- gamemoderun --version ----")
        lines.append(res_ver.output or ("OK" if res_ver.success else "errore"))

        body = "\n".join(lines)
        ok = res_test.success and res_ver.success
        self._run_dialog(dialogs.command_output(
            self, "Test del daemon", body, ok))

    def _show_help(self) -> None:
        self._run_dialog(dialogs.info(
            self,
            "Guida rapida",
            "Caricamento privilegiato delle configurazioni\n\n"
            "Questo strumento gestisce il file utente in "
            "$XDG_CONFIG_HOME/gamemode.ini.\n\n"
            "Nota: le opzioni [gpu] vengono applicate dal daemon solo se il "
            "file si trova in /etc/gamemode.ini (implicano l'assunzione di "
            "responsabilità).\n\n"
            "Per usare renice e core parking è necessario appartenere al "
            "gruppo 'gamemode'.",
        ))

    # -- helper to run a dialog -------------------------------------------
    def _run_dialog(self, dlg: Adw.MessageDialog) -> None:
        dlg.present(self)

    # -- navigation --------------------------------------------------------
    def _navigate(self, delta: int) -> None:
        target = self._current + delta
        if not (0 <= target < len(STEPS_META)):
            return
        self._current = target
        self.stack.set_visible_child_name(f"step-{target}")
        if target == 3:
            self._refresh_summary()
        self._update_controls()

    def _update_controls(self) -> None:
        self.progress_label.set_text(STEPS_META[self._current][1])
        self._go_back.set_sensitive(self._current > 0)
        self._go_next.set_sensitive(self._current < len(STEPS_META) - 1)
        if self._current >= 3:
            self._go_next.set_label("Chiudi")
        else:
            self._go_next.set_label("Avanti")

    # -- summary refresh ---------------------------------------------------
    def _refresh_summary(self) -> None:
        refresh = getattr(self._summary_page, "_refresh_summary", None)
        if callable(refresh):
            refresh()

    # -- dirty tracking ----------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True

    def _on_close_request(self, *_):
        if self._saved:
            return False
        if self._dirty:
            dlg = dialogs.confirm(
                self,
                "Modifiche non salvate",
                "Sono presenti modifiche non salvate. Uscire senza salvare?",
                confirm_label="Esci senza salvare",
            )
            dlg.present(self)
            dlg.connect("response", self._closed_confirmed)
            return True
        return False

    def _closed_confirmed(self, dlg, response: str) -> None:
        dlg.close()
        if response == "Esci senza salvare":
            self._saved = True
            self.close()

    # ------------------------------------------------------------------
    # Actions (also used by the step pages)
    # ------------------------------------------------------------------
    def do_save(self) -> None:
        try:
            content = self.controller.render()
        except Exception as exc:  # validation/render errors
            self._run_dialog(dialogs.error(
                self, "Impossibile generare la configurazione", str(exc)))
            return

        try:
            self.cm.save(content)
        except OSError as exc:
            self._run_dialog(dialogs.error(
                self,
                "Errore durante il salvataggio",
                f"La scrittura è fallita ed è stato ripristinato il backup "
                f"precedente.\n\nDettagli: {exc}",
            ))
            return

        self._dirty = False
        self._saved = True
        self._navigate(1)  # -> step 5
        self._show_notification("Configurazione salvata correttamente.")

    def do_restore_backup(self) -> None:
        dlg = dialogs.confirm(
            self, "Ripristina backup",
            "Ripristinare la configurazione precedente (gamemode.ini.bak)?",
            confirm_label="Ripristina",
        )
        dlg.present(self)
        dlg.connect("response", self._restore_backup_response)

    def _restore_backup_response(self, dlg, response: str) -> None:
        dlg.close()
        if response != "Ripristina":
            return
        ok = self.cm.rollback_from_backup()
        if ok:
            self.controller.load(self.config_path)
            self._mark_dirty()
            self._refresh_summary()
            self._show_notification("Backup ripristinato.")
        else:
            self._run_dialog(dialogs.error(
                self, "Nessun backup", "Non esiste un backup precedente."))

    def do_restore_orig(self) -> None:
        dlg = dialogs.confirm(
            self, "Ripristina originale",
            "Ripristinare la configurazione originale memorizzata in "
            "gamemode.ini.orig?",
            confirm_label="Ripristina",
        )
        dlg.present(self)
        dlg.connect("response", self._restore_orig_response)

    def _restore_orig_response(self, dlg, response: str) -> None:
        dlg.close()
        if response != "Ripristina":
            return
        ok = self.cm.restore_from_orig()
        if ok:
            self.controller.load(self.config_path)
            self._mark_dirty()
            self._refresh_summary()
            self._show_notification("Configurazione originale ripristinata.")
        else:
            self._run_dialog(dialogs.error(
                self, "Nessun originale",
                "Non esiste gamemode.ini.orig."))

    def do_add_group(self, on_done=None) -> None:
        res = gm.add_user_to_group()
        dlg = dialogs.command_output(
            self,
            "Aggiunta al gruppo 'gamemode'",
            res.output,
            res.success,
        )
        dlg.present(self)
        dlg.connect("response", lambda *_: on_done() if on_done else None)
        if res.success:
            # Only when the user was actually added does a logout/log-in help.
            dlg.connect("response", lambda *_: self._run_dialog(dialogs.info(
                self,
                "Logout richiesto",
                "Sei stato aggiunto al gruppo 'gamemode'. Per rendere "
                "effettivo il cambiamento è necessario eseguire il "
                "logout/login. Il riavvio del daemon da solo non basta.")))

    def do_restart_daemon(self) -> None:
        res = gm.restart_daemon()
        dlg = dialogs.command_output(
            self, "Riavvio del daemon", res.output, res.success)
        dlg.present(self)

    # -- misc --------------------------------------------------------------
    def _show_notification(self, message: str) -> None:
        toast = Adw.Toast(title=message)
        self.toast_overlay.add_toast(toast)


def gtk_spacer() -> Gtk.Box:
    box = Gtk.Box()
    box.set_hexpand(True)
    return box