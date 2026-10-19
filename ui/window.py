"""General UI: the main window that gathers every section page.

The window is intentionally thin. It builds the header (help + language menu),
asks the section registry for one page per section, and shows them in a
ViewStack together with the summary page (file preview + save / restore /
factory reset). All visible text goes through ``i18n.tr``.
"""

from __future__ import annotations

import getpass
import importlib
import os
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

import i18n, initializer
from i18n import tr
from initializer import App, SECTION_MODULES
from sections.daemon import core as daemon

# The application stylesheet is owned by the general window.
_STYLE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "style.css")


# --- small dialog helpers ---------------------------------------------------

def _make_dialog(parent, heading: str, body: str, responses: List[str],
                 default: Optional[str] = None) -> Adw.MessageDialog:
    dialog = Adw.MessageDialog(transient_for=parent)
    dialog.set_heading(heading)
    dialog.set_body(body)
    for response in responses:
        dialog.add_response(response, response)
    if default:
        dialog.set_default_response(default)
    return dialog


def info_dialog(parent, heading: str, body: str, close: Optional[str] = None) -> Adw.MessageDialog:
    close = close or tr("dlg.ok")
    return _make_dialog(parent, heading, body, [close], default=close)


def confirm_dialog(parent, heading: str, body: str,
                   confirm: Optional[str] = None) -> Adw.MessageDialog:
    confirm = confirm or tr("dlg.confirm")
    return _make_dialog(parent, heading, body, [confirm, tr("dlg.cancel")],
                        default=tr("dlg.cancel"))


def error_dialog(parent, heading: str, body: str) -> Adw.MessageDialog:
    return _make_dialog(parent, heading, body, [tr("dlg.close")], default=tr("dlg.close"))


def _install_css() -> bool:
    """Register the application stylesheet; True if it was added."""
    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(_STYLE_FILE)
        display = Gdk.Display.get_default()
        if display is None:
            return False
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        return True
    except Exception:
        return False


# --- summary page -----------------------------------------------------------

class SummaryPage(Gtk.Box):
    """Read-only preview of the gamemode.ini content that will be written.

    The save / restore / factory-reset actions live in the general window's
    always-visible action bar, so they are available on every tab.
    """

    def __init__(self, application_core, config_path: str,
                 base_path: Optional[str]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.application_core = application_core

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header.append(Gtk.Label(label=tr("step.summary.title"), xalign=0.0,
                                css_classes=["title-2"]))
        header.append(Gtk.Label(label=tr("step.summary.subtitle"), xalign=0.0,
                                css_classes=["dim-label"], wrap=True))
        self.append(header)
        if config_path:
            self.append(Gtk.Label(label=tr("summary.path").format(path=config_path),
                                  xalign=0.0, wrap=True, css_classes=["dim-label"]))
        if base_path:
            self.append(Gtk.Label(label=tr("summary.base").format(path=base_path),
                                  xalign=0.0, wrap=True, css_classes=["dim-label"]))

        scroller = Gtk.ScrolledWindow(vexpand=True)
        view = Gtk.TextView(editable=False, monospace=True,
                            wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self._buffer = view.get_buffer()
        scroller.set_child(view)
        self.append(scroller)
        self.refresh()

    def refresh(self) -> None:
        self._buffer.set_text(self.application_core.render())


# --- main window ------------------------------------------------------------

class MainWindow(Adw.ApplicationWindow):
    """Main window: header (help + language) + a page per section + summary."""

    def __init__(self, app_state: App, application=None) -> None:
        super().__init__(application=application, title=tr("window.title"))
        self.set_default_size(1180, 820)
        self.state = app_state
        self.core = app_state.core
        self.config_path = app_state.config_path
        self.base_path = app_state.base_path
        self._dirty = False
        self.pages: Dict[str, object] = {}

        # The store drives the dirty flag and the dependent-option gating.
        if self.core.store is not None:
            self.core.store.subscribe(self._on_store_state)

        self._build_ui()
        for message in i18n.describe_lang_errors():
            self.toast_overlay.add_toast(Adw.Toast(title=message))

    def _static_page(self, section_id: str):
        """Build a stateless section page (no state/initializer), by convention."""
        ui_module = importlib.import_module(f"sections.{section_id}.ui")
        return ui_module.build_page(self)

    def _build_action_bar(self) -> Gtk.Widget:
        """Always-visible action bar: save / restore previous / factory reset.

        It is part of the general UI, so the same three actions are available on
        every tab (sections have no Save button of their own).
        """
        bar = Gtk.ActionBar()
        restore_previous = Gtk.Button(label=tr("btn.restore_backup"))
        restore_previous.connect("clicked", lambda *_: self.do_restore_previous())
        restore_original = Gtk.Button(label=tr("btn.restore_orig"))
        restore_original.connect("clicked", lambda *_: self.do_factory_reset())
        save = Gtk.Button(label=tr("btn.save"))
        save.add_css_class("suggested-action")
        save.set_tooltip_text(tr("btn.save.tooltip"))
        save.connect("clicked", lambda *_: self.do_save())
        # pack_end goes right-to-left: leftmost first is restore_previous.
        bar.pack_end(save)
        bar.pack_end(restore_original)
        bar.pack_end(restore_previous)
        return bar

    def _build_ui(self) -> None:
        self.set_title(tr("window.title"))
        _install_css()

        toolbar = Adw.ToolbarView()
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(toolbar)
        self.set_content(self.toast_overlay)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        toolbar.add_bottom_bar(self._build_action_bar())
        help_button = Gtk.Button(icon_name="help-about-symbolic")
        help_button.set_tooltip_text(tr("header.help.tooltip"))
        help_button.connect(
            "clicked",
            lambda *_: info_dialog(self, tr("dlg.help.title"),
                                   tr("dlg.help.body")).present())
        header.pack_end(help_button)
        header.pack_end(self._build_language_button())

        self.stack = Adw.ViewStack()
        if hasattr(self.stack, "set_transition_type"):
            self.stack.set_transition_type(
                Adw.ViewStackTransitionType.SLIDE_LEFT_RIGHT)

        # Presentation (static) first, then one page per stateful section, then
        # the summary, then the daemon (static) last.
        self.presentation_page = self._static_page("presentation")
        self.pages["presentation"] = self.presentation_page
        self.stack.add_titled(self.presentation_page, "presentation",
                              tr("tab.presentation"))

        for section_id, (_core_class, _initializer) in SECTION_MODULES.items():
            ui_module = importlib.import_module(f"sections.{section_id}.ui")
            section_core = next(section for section in self.core.sections
                                if section.section_id == section_id)
            page = ui_module.build_page(section_core)
            self.pages[section_id] = page
            self.stack.add_titled(page, section_id, tr(ui_module.TAB_TITLE_ID))

        self.summary_page = SummaryPage(self.core, self.config_path, self.base_path)
        self.pages["summary"] = self.summary_page
        self.stack.add_titled(self.summary_page, "summary", tr("tab.summary"))

        self.daemon_page = self._static_page("daemon")
        self.pages["daemon"] = self.daemon_page
        self.stack.add_titled(self.daemon_page, "daemon", tr("tab.daemon"))

        first_section = next(iter(SECTION_MODULES))
        self.stack.set_visible_child_name(first_section)

        switcher = Adw.ViewSwitcher(stack=self.stack)
        if hasattr(Adw, "ViewSwitcherPolicy"):
            switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_margin_top(12)
        wrapper.set_margin_bottom(12)
        wrapper.set_margin_start(16)
        wrapper.set_margin_end(16)
        wrapper.append(self.stack)
        toolbar.set_content(wrapper)
        self.connect("close-request", self._on_close_request)

    def _build_language_button(self) -> Gtk.Widget:
        """Header button with the menu of available languages."""
        button = Gtk.MenuButton()
        button.set_icon_name("preferences-desktop-locale-symbolic")
        button.set_tooltip_text(tr("header.lang.tooltip"))
        menu = Gio.Menu()
        for code, label in self.core.language_menu():
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value("app.set-lang",
                                             GLib.Variant.new_string(code))
            menu.append_item(item)
        button.set_menu_model(menu)
        return button

    # -- dirty tracking ------------------------------------------------------
    def _on_store_state(self, root: dict) -> None:
        """Sync the dirty flag and refresh the dependent-option gating."""
        self._dirty = bool(root.get("dirty", False))
        for page in self.pages.values():
            if hasattr(page, "refresh_gating"):
                page.refresh_gating()

    def _refresh_all(self) -> None:
        """Re-sync every page with the (possibly reloaded) section state."""
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                page.refresh()

    def _on_close_request(self, *_):
        """Ask for confirmation when closing with unsaved changes."""
        if not self._dirty:
            return False
        dialog = confirm_dialog(self, tr("dlg.unsaved.title"), tr("dlg.unsaved.body"),
                                confirm=tr("dlg.unsaved.exit"))
        dialog.present()
        dialog.connect("response", self._closed_confirmed)
        return True

    def _closed_confirmed(self, dialog, response: str) -> None:
        """Close the window only if the user chose to discard the changes."""
        dialog.close()
        if response == tr("dlg.unsaved.exit"):
            self._dirty = False
            self.close()

    # -- shared actions ------------------------------------------------------
    def do_save(self) -> None:
        """Save the combined state atomically and warn about the daemon restart."""
        try:
            self.core.save()
        except Exception as exc:
            body = tr("dlg.save_error.body").format(error=exc)
            error_dialog(self, tr("dlg.save_error.title"), body).present()
            return
        self._refresh_all()
        self._dirty = False
        info_dialog(self, tr("dlg.save_daemon.title"),
                    tr("dlg.save_daemon.body")).present()

    def do_restore_previous(self) -> None:
        """Restore the previous state after confirmation."""
        self._confirm_restore("dlg.restore_bak", "btn.restore_backup",
                              self.core.restore_previous)

    def do_factory_reset(self) -> None:
        """Restore GameMode's pristine configuration after confirmation."""
        self._confirm_restore("dlg.restore_orig", "btn.restore_orig",
                              self.core.restore_factory)

    def _confirm_restore(self, prefix: str, confirm_id: str, restore) -> None:
        dialog = confirm_dialog(self, tr(f"{prefix}.title"), tr(f"{prefix}.body"),
                                confirm=tr(confirm_id))
        dialog.present()
        dialog.connect("response", lambda d, resp: self._restore_response(
            d, resp, prefix, confirm_id, restore))

    def _restore_response(self, dialog, response: str, prefix: str,
                          confirm_id: str, restore) -> None:
        dialog.close()
        if response != tr(confirm_id):
            return
        if restore():
            initializer.reload(self.state)
            self._refresh_all()
            self._dirty = False
            self.toast_overlay.add_toast(Adw.Toast(title=tr(f"{prefix}.ok")))
        else:
            info_dialog(self, tr(f"{prefix}.title"),
                        tr(f"{prefix}.none")).present()

    # -- daemon actions ------------------------------------------------------
    def do_restart_daemon(self) -> None:
        """Restart the daemon and show the command + output in the console."""
        self._show_daemon_result(daemon.restart_daemon(),
                                 "systemctl --user restart gamemoded")

    def run_daemon_tests(self) -> None:
        """Run the daemon diagnostics and version, showing them in the console."""
        self._show_daemon_result(daemon.test_daemon(), "gamemoded -t")
        self._show_daemon_result(daemon.daemon_version(), "gamemoded --version")

    def do_add_group(self) -> None:
        """Add the current user to the gamemode group and refresh the status."""
        result = daemon.add_user_to_group()
        self._show_daemon_result(result, f"usermod -aG gamemode {getpass.getuser()}")
        if result.success:
            self.pages["daemon"].show_output(tr("dlg.logout.body"))
        self.pages["daemon"].refresh_group()

    def _show_daemon_result(self, result, fallback_command: str) -> None:
        page = self.pages["daemon"]
        page.show_command(result.command or fallback_command)
        page.show_output(result.output)


# --- application ------------------------------------------------------------

class Application(Adw.Application):
    """GTK application: owns the window and the language action."""

    def __init__(self) -> None:
        super().__init__(application_id="io.github.gamemodegui.GameModeGui",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._window: Optional[MainWindow] = None
        action = Gio.SimpleAction.new_stateful(
            "set-lang", GLib.VariantType.new("s"),
            GLib.Variant.new_string(i18n.current_lang()))
        action.connect("change-state", self._on_set_lang)
        self.add_action(action)

    def _on_set_lang(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        code = value.get_string()
        if code == action.get_state().get_string():
            return
        action.set_state(value)
        i18n.save_lang(code)  # the saved choice takes precedence over everything
        if self._window is not None:
            info_dialog(self._window, tr("dlg.lang.title"),
                        tr("dlg.lang.body")).present()

    def do_activate(self) -> None:
        i18n.ensure_settings()
        if self._window is None:
            self._window = MainWindow(initializer.build_app(), application=self)
        self._window.present()


def run(argv: List[str]) -> int:
    """Entry point used by :mod:`main` and the repo shim."""
    return Application().run(argv)
