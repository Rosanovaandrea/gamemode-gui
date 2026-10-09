"""GTK4/Libadwaita interface — a single file, with tabs generated from the data.

File layout (to ease navigation):

  1. CHAPTER 1 — imports, constants, dialogs, console style
  2. CHAPTER 2 — session controller (in-memory state)
  3. CHAPTER 3 — option tabs (generated from options.json)
  4. CHAPTER 4 — Summary tab (preview + save + restores)
  5. CHAPTER 5 — Daemon tab (console, restart, tests, gamemode group)
  6. CHAPTER 5b — Presentation tab (data-driven content)
  7. CHAPTER 6 — helpers shared between the tabs
  8. CHAPTER 7 — main window (ViewStack + ViewSwitcher tabs)
  9. CHAPTER 8 — application (Gtk entry point)

Visible strings ALWAYS go through core.tr() (i18n via XML), never hardcoded.
The tabs and options come from `options.json`: adding an entry there is enough.
"""

from __future__ import annotations

import getpass
import os
import sys
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

import core
from core import Category, ConfigManager, OptionSpec, tr
from widgets import OptionRow


# ===========================================================================
# CHAPTER 1 — global constants, dialogs, console style
# ===========================================================================

# Visible tabs: the categories (from options.json) + Summary and Daemon.
TABS_META = [("presentation", tr("tab.presentation"))] + [
    (cat.id, tr(cat.tab_id)) for cat in core.CATEGORIES
] + [
    ("summary", tr("tab.summary")),
    ("daemon", tr("tab.daemon")),
]


def resolve_config_path() -> str:
    """Path of the gamemode.ini file managed by the GUI.

    Default: /etc/gamemode.ini (single, privileged path). Overridable with the
    GAMEMODE_CONFIG variable for tests.
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
    """Dialog for "file not found" / failed restore."""
    return info_dialog(parent, heading, body, close=tr("dlg.close"))


# Application style: loaded from the `style.css` file next to the code
# (Daemon tab console, selected choice with accent background, "+"/"−" stepper
# texts in the accent colour).
_STYLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")


def install_app_css() -> bool:
    """Register the app style from `style.css`. Returns True if it was added."""
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


# ===========================================================================
# CHAPTER 2 — session controller (in-memory state)
# ===========================================================================

class SessionController:
    """In-memory state: the current value of every option.

    The "effective" values are the result of the merge between the file installed
    by the package (base) and the override in /etc, as the daemon does.
    """

    def __init__(self) -> None:
        self.values = {spec.id: spec.default for spec in core.OPTIONS}
        self.base_path: Optional[str] = None
        self.base_comments: dict = {}
        self.on_change: Optional[Callable[[], None]] = None

    def load_from_path(self, override_path: str, base_path: Optional[str] = None) -> None:
        """Load the effective values (installed base + override)."""
        self.base_path = base_path if base_path and os.path.isfile(base_path) else None
        self.base_comments = core.load_base_comments(self.base_path)
        self.values = core.load_effective_values(self.base_path, override_path)
        # If neither the override nor the base exist, try the saved session.
        if not os.path.isfile(override_path) and self.base_path is None:
            restored = core.load_session(override_path)
            if restored is not None:
                for spec in core.OPTIONS:
                    if spec.id in restored:
                        self.values[spec.id] = core.coerce_value(spec, restored[spec.id])

    def set_option(self, spec_id: str, value) -> None:
        self.values[spec_id] = value
        if self.on_change:
            self.on_change()

    def get_value(self, spec_id: str):
        return self.values.get(spec_id)

    def render(self) -> str:
        return core.render_ini(self.values, self.base_comments)


# ===========================================================================
# CHAPTER 3 — option tabs (generated from the categories)
# ===========================================================================

class OptionTab(Gtk.Box):
    """Tab with all the options of a category + Save button."""

    def __init__(self, category: Category, controller: SessionController, actions) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.category = category
        self.controller = controller
        self.actions = actions
        self.rows: List[OptionRow] = []

        self.append(_header(tr(category.title_id), tr(category.subtitle_id)))
        toggle_specs = [s for s in category.options if s.type == "toggle_entry"]
        if toggle_specs:
            self.append(_build_toggle_card(category, toggle_specs, controller, self.rows))
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
        """Realign all rows with the controller state."""
        for row in self.rows:
            _populate_row(row, self.controller)
        self.refresh_gating()

    def refresh_gating(self) -> None:
        """Enable/disable options based on their dependencies."""
        values = self.controller.values
        for row in self.rows:
            dep = getattr(row.spec, "depends_on", None)
            if dep:
                row.set_enabled(core.dependency_met(row.spec, values))


# ===========================================================================
# CHAPTER 4 — Summary tab (preview + save + restores)
# ===========================================================================

class SummaryTab(Gtk.Box):
    """File preview + Save / restore buttons."""

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
# CHAPTER 5 — Daemon tab (console, restart, tests, gamemode group)
# ===========================================================================

class DaemonTab(Gtk.Box):
    """Daemon management: restart, tests, gamemode group and simulated console."""

    def __init__(self, actions) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.actions = actions

        self.append(_header(tr("tab.daemon.title"), tr("tab.daemon.subtitle")))

        # Box with the daemon actions.
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

        # gamemode group box.
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

        # Simulated console: always visible, shows the commands and their raw
        # output (without any success/error verdict).
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

    # -- simulated console ----------------------------------------------------
    def clear_console(self) -> None:
        self._console_buf.set_text("")

    def append_console(self, text: str) -> None:
        """Append text to the console and scroll to the bottom."""
        if text is None:
            return
        end = self._console_buf.get_end_iter()
        self._console_buf.insert(end, text)
        if not text.endswith("\n"):
            self._console_buf.insert(self._console_buf.get_end_iter(), "\n")
        self._console_view.scroll_to_iter(
            self._console_buf.get_end_iter(), 0.0, False, 0.0, 0.0)

    def refresh_group(self) -> None:
        """Update the gamemode group status."""
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
# CHAPTER 5b — Presentation tab (data-driven content)
# ===========================================================================

class PresentationTab(Gtk.Box):
    """Introductory page: what GameMode is, how to use it, warnings.

    The blocks and texts come from ``presentation.json`` + the language files, so
    adding/editing content needs no code.
    """

    def __init__(self, presentation=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.presentation = presentation or core.PRESENTATION
        pres = self.presentation

        self.append(_header(tr(pres.title_id), tr(pres.subtitle_id)))

        scroller = Gtk.ScrolledWindow(vexpand=True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(4)
        content.set_margin_bottom(4)
        for block in pres.blocks:
            content.append(_presentation_block(block))
        scroller.set_child(content)
        self.append(scroller)


def _presentation_block(block) -> Gtk.Widget:
    """A Presentation block: heading + text (card with icon if a warning)."""
    heading = Gtk.Label(label=tr(block.heading_id), xalign=0.0, wrap=True,
                        css_classes=["heading"])
    body = Gtk.Label(label=tr(block.body_id), xalign=0.0, wrap=True, selectable=True)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    if block.warning:
        box.add_css_class("card")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for margin in ("top", "bottom", "start", "end"):
            getattr(inner, f"set_margin_{margin}")(12)
        icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        icon.set_valign(Gtk.Align.START)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        text.set_hexpand(True)
        text.append(heading)
        text.append(body)
        inner.append(icon)
        inner.append(text)
        box.append(inner)
    else:
        box.append(heading)
        box.append(body)
    return box


# ===========================================================================
# CHAPTER 6 — helpers shared between the tabs
# ===========================================================================

def _header(title: str, subtitle: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.append(Gtk.Label(label=title, xalign=0.0, css_classes=["title-2"]))
    box.append(Gtk.Label(label=subtitle, xalign=0.0,
                         css_classes=["dim-label"], wrap=True))
    return box


def _build_option_list(controller: SessionController, category: Category,
                       rows: List[OptionRow]) -> Gtk.Widget:
    """Build the scrollable list of rows for a category."""
    scroller = Gtk.ScrolledWindow(vexpand=True)
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    listbox.add_css_class("boxed-list")

    for spec in category.options:
        if spec.type == "toggle_entry":
            continue  # these go into the top card (see _build_toggle_card)
        row = OptionRow(spec)
        _populate_row(row, controller)
        row._on_change = lambda spec_id, _r=row: _apply_row_change(
            controller, _r, spec_id)
        rows.append(row)
        listbox.append(row)

    scroller.set_child(listbox)
    return scroller


def _build_toggle_card(category: Category, specs: List[OptionSpec],
                       controller: SessionController,
                       rows: List[OptionRow]) -> Gtk.Widget:
    """Card at the top of the tab with the "toggle_entry" switches.

    Each switch adds/removes a fixed string (``entry``) to/from the target list
    (``target``): the list itself shows only the other scripts.
    """
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("card")
    card.set_margin_top(4)
    card.set_margin_bottom(4)
    card.set_margin_start(4)
    card.set_margin_end(4)
    if category.toggle_card_id:
        title = Gtk.Label(label=tr(category.toggle_card_id), xalign=0.0,
                          css_classes=["heading"])
        title.set_margin_start(12)
        title.set_margin_top(8)
        title.set_margin_bottom(4)
        card.append(title)

    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    for spec in specs:
        row = OptionRow(spec)
        _populate_row(row, controller)
        row._on_change = lambda spec_id, _r=row: _apply_row_change(
            controller, _r, spec_id)
        rows.append(row)
        listbox.append(row)
    card.append(listbox)
    return card


def _populate_row(row: OptionRow, controller: SessionController) -> None:
    """Sync a row with the current state, without propagating events."""
    row._suppress = True
    row.set_value(controller.get_value(row.spec.id))
    row._suppress = False


def _apply_row_change(controller: SessionController, row: OptionRow,
                      spec_id: str) -> None:
    controller.set_option(spec_id, row.get_value())


# ===========================================================================
# CHAPTER 7 — Main window (tabbed navigation)
# ===========================================================================

class GameModeWindow(Adw.ApplicationWindow):
    """Main window: header with the tab switcher + tab stack."""

    def __init__(self, *args, **kwargs) -> None:
        application = kwargs.pop("application", None) or (args[0] if args else None)
        super().__init__(application=application, title=tr("window.title"), **kwargs)
        self.set_default_size(1180, 820)

        self.config_path = resolve_config_path()
        # Base = gamemode.ini installed by the package (varies per distro).
        self.base_path = core.resolve_base_path()
        self.base_content = self._read_text(self.base_path)
        self.cm = ConfigManager(self.config_path, orig_seed=self.base_content)
        self.controller = SessionController()
        self.controller.on_change = self._mark_dirty
        self._dirty = False

        self._init_data()
        self._build_ui()
        self._warn_lang_config()

    def _warn_lang_config(self) -> None:
        """Warn (non-blocking) if the language configuration has errors."""
        for message in core.describe_lang_errors():
            self._show_toast(message)

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

    # -- UI construction --------------------------------------------------------
    def _build_ui(self) -> None:
        self.set_title(tr("window.title"))
        install_app_css()

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
        header.pack_end(self._build_lang_button())

        # Tab stack.
        self.stack = Adw.ViewStack()
        if hasattr(self.stack, "set_transition_type"):
            self.stack.set_transition_type(
                Adw.ViewStackTransitionType.SLIDE_LEFT_RIGHT)

        # Tabs: Presentation (default) + one per category + Summary/Daemon.
        self.option_tabs = {}
        self.presentation_tab = PresentationTab()
        pages = {"presentation": self.presentation_tab}
        for cat in core.CATEGORIES:
            tab = OptionTab(cat, self.controller, self)
            self.option_tabs[cat.id] = tab
            setattr(self, f"{cat.id}_tab", tab)  # e.g. general_tab, gpu_tab
            pages[cat.id] = tab

        self.summary_tab = SummaryTab(self.controller, self, self.config_path,
                                      self.base_path)
        self.daemon_tab = DaemonTab(self)
        pages["summary"] = self.summary_tab
        pages["daemon"] = self.daemon_tab

        for name, title in TABS_META:
            self.stack.add_titled(pages[name], name, title)

        # At startup the Presentation tab opens (first tab).
        self.stack.set_visible_child_name("presentation")

        switcher = Adw.ViewSwitcher(stack=self.stack)
        if hasattr(Adw, "ViewSwitcherPolicy"):
            switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Margins around the content area (general window padding).
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_margin_top(12)
        wrapper.set_margin_bottom(12)
        wrapper.set_margin_start(16)
        wrapper.set_margin_end(16)
        wrapper.append(self.stack)
        toolbar.set_content(wrapper)
        self.connect("close-request", self._on_close_request)

    def _build_lang_button(self) -> Gtk.Widget:
        """Header button with the menu of available languages.

        The selected entry is the active one; choosing another saves it
        (action `app.set-lang`) pending the next start.
        """
        button = Gtk.MenuButton()
        button.set_icon_name("preferences-desktop-locale-symbolic")
        button.set_tooltip_text(tr("header.lang.tooltip"))
        menu = Gio.Menu()
        # Languages and names come from the config file / the XML files.
        for code, label in core.available_langs():
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value("app.set-lang",
                                             GLib.Variant.new_string(code))
            menu.append_item(item)
        button.set_menu_model(menu)
        return button

    def notify_language_restart(self) -> None:
        """Warn that the new language will be applied on the next start."""
        self._run_dialog(info_dialog(self, tr("dlg.lang.title"),
                                     tr("dlg.lang.body")))

    # -- dirty tracking ---------------------------------------------------------
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

    # -- shared actions ---------------------------------------------------------
    def _refresh_all(self) -> None:
        for tab in self.option_tabs.values():
            tab.refresh()
        self.summary_tab.refresh()

    def do_save(self) -> None:
        """Save the active file (atomic commit) + JSON session."""
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
        # Warn that the changes take effect only after restarting the daemon.
        self._run_dialog(info_dialog(self, tr("dlg.save_daemon.title"),
                                     tr("dlg.save_daemon.body")))

    def do_restore_backup(self) -> None:
        """Ask for confirmation and restore the previous `.bak`."""
        self._confirm_restore("dlg.restore_bak", "btn.restore_backup",
                              self.cm.rollback_from_backup)

    def do_restore_orig(self) -> None:
        """Ask for confirmation and restore the pristine `.orig`."""
        self._confirm_restore("dlg.restore_orig", "btn.restore_orig",
                              self.cm.restore_from_orig)

    def _confirm_restore(self, prefix: str, confirm_id: str, restore) -> None:
        dlg = confirm_dialog(self, tr(f"{prefix}.title"), tr(f"{prefix}.body"),
                             confirm=tr(confirm_id))
        dlg.present()
        dlg.connect("response", lambda d, resp: self._restore_response(
            d, resp, prefix, confirm_id, restore))

    def _restore_response(self, dlg, response: str, prefix: str, confirm_id: str,
                          restore) -> None:
        dlg.close()
        if response != tr(confirm_id):
            return
        if restore():
            self.controller.load_from_path(self.config_path, self.base_path)
            self._refresh_all()
            self._mark_dirty()
            self._show_toast(tr(f"{prefix}.ok"))
        else:
            self._run_dialog(missing_dialog(self, tr(f"{prefix}.title"),
                                            tr(f"{prefix}.none")))

    def do_add_group(self, on_done=None) -> None:
        user = getpass.getuser()
        res = core.add_user_to_group()
        console = self.daemon_tab
        console.append_console(tr("daemon.console.cmd").format(
            cmd=res.command or f"usermod -aG gamemode {user}"))
        console.append_console(res.output)
        if res.success:
            console.append_console(tr("dlg.logout.body"))
        if on_done:
            on_done()

    def do_restart_daemon(self) -> None:
        res = core.restart_daemon()
        console = self.daemon_tab
        console.append_console(tr("daemon.console.cmd").format(
            cmd=res.command or "systemctl --user restart gamemoded"))
        console.append_console(res.output)

    def run_tests(self) -> None:
        """Run the daemon test commands and show their output in the console."""
        console = self.daemon_tab
        res_test = core.test_daemon()
        console.append_console(tr("daemon.console.cmd").format(
            cmd=res_test.command or "gamemoded -t"))
        console.append_console(res_test.output)
        res_ver = core.daemon_version()
        console.append_console(tr("daemon.console.cmd").format(
            cmd=res_ver.command or "gamemoded --version"))
        console.append_console(res_ver.output)

    def _show_help(self) -> None:
        self._run_dialog(info_dialog(self, tr("dlg.help.title"), tr("dlg.help.body")))

    def _run_dialog(self, dlg: Adw.MessageDialog) -> None:
        dlg.present()

    def _show_toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=message))


# ===========================================================================
# CHAPTER 8 — Application (Gtk entry point)
# ===========================================================================

class GameModeApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.gamemodegui.GameModeGui",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._window: Optional[GameModeWindow] = None
        self._install_actions()

    def _install_actions(self) -> None:
        """Stateful action for the language choice (radio entries)."""
        action = Gio.SimpleAction.new_stateful(
            "set-lang", GLib.VariantType.new("s"),
            GLib.Variant.new_string(core.current_lang()))
        action.connect("change-state", self._on_set_lang)
        self.add_action(action)

    def _on_set_lang(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        code = value.get_string()
        if code == action.get_state().get_string():
            return
        action.set_state(value)
        core.save_lang(code)  # the saved choice takes precedence over everything
        if self._window is not None:
            self._window.notify_language_restart()

    def do_activate(self) -> None:
        core.ensure_settings()  # create/update settings.json (language list)
        if self._window is None:
            self._window = GameModeWindow(application=self)
        self._window.present()


def main() -> int:
    """Entry point to launch the application."""
    app = GameModeApplication()
    return app.run(sys.argv)
