"""View of the Daemon section (stateless).

Daemon actions (restart, diagnostics, group) plus a simulated console that shows
the raw output of every command. The actions live in the section core; the
window connects them (see :class:`ui.MainWindow`).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from i18n.translator import tr
from services.daemon import group_exists, user_in_group
from ui.widgets.page_header import PageHeader


class DaemonPage(Gtk.Box):
    """Daemon management: restart, tests, gamemode group and simulated console."""

    def __init__(self, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add_css_class("daemon-page")
        self.window = window
        self.append(PageHeader("tab.daemon.title", "tab.daemon.subtitle"))
        self.append(self._actions_card())
        self.append(self._group_card())
        self.append(self._console_header())
        self.append(self._console())
        self.refresh_group()

    def _actions_card(self) -> Gtk.Widget:
        """Card with the daemon actions: restart and run the diagnostics."""
        card = self._card()
        restart = Gtk.Button(label=tr("btn.restart_daemon"))
        restart.add_css_class("suggested-action")
        restart.set_halign(Gtk.Align.START)
        restart.connect("clicked", lambda *_: self.window.do_restart_daemon())
        test = Gtk.Button(label=tr("btn.test_daemon"))
        test.set_halign(Gtk.Align.START)
        test.connect("clicked", lambda *_: self.window.run_daemon_tests())
        card.append(restart)
        card.append(test)
        return card

    def _group_card(self) -> Gtk.Widget:
        """Card showing the gamemode-group status and the join button."""
        card = self._card()
        card.append(Gtk.Label(label=tr("daemon.group.title"), xalign=0.0,
                              css_classes=["heading"]))
        self.group_status = Gtk.Label(label="", xalign=0.0, wrap=True,
                                      css_classes=["dim-label"])
        card.append(self.group_status)
        self.add_group_button = Gtk.Button(label=tr("btn.add_group"))
        self.add_group_button.set_halign(Gtk.Align.START)
        self.add_group_button.connect("clicked", lambda *_: self.window.do_add_group())
        card.append(self.add_group_button)
        return card

    def _console_header(self) -> Gtk.Widget:
        """Header of the console: title + clear button."""
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.append(Gtk.Label(label=tr("daemon.console.title"), xalign=0.0,
                                hexpand=True, css_classes=["heading"]))
        clear = Gtk.Button(label=tr("daemon.console.clear"))
        clear.add_css_class("flat")
        clear.connect("clicked", lambda *_: self.clear_console())
        header.append(clear)
        return header

    def _console(self) -> Gtk.Widget:
        """Read-only, monospaced console that shows the raw command output."""
        self._console_view = Gtk.TextView(editable=False,
                                          wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                          cursor_visible=False)
        self._console_view.add_css_class("console")
        self._console_buffer = self._console_view.get_buffer()
        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.set_child(self._console_view)
        return scroller

    @staticmethod
    def _card() -> Gtk.Box:
        """Create an empty card (rounded box with small internal margins)."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card")
        card.add_css_class("daemon-card")
        return card

    # -- console -------------------------------------------------------------
    def clear_console(self) -> None:
        """Empty the console text buffer."""
        self._console_buffer.set_text("")

    def append_console(self, text: str) -> None:
        """Append text to the console and scroll to the bottom."""
        if not text:
            return
        end = self._console_buffer.get_end_iter()
        self._console_buffer.insert(end, text)
        if not text.endswith("\n"):
            self._console_buffer.insert(self._console_buffer.get_end_iter(), "\n")
        self._console_view.scroll_to_iter(
            self._console_buffer.get_end_iter(), 0.0, False, 0.0, 0.0)

    def show_command(self, command: str) -> None:
        """Print the command line that was run, in the console format."""
        self.append_console(tr("daemon.console.cmd").format(cmd=command))

    def show_output(self, output: str) -> None:
        self.append_console(output)

    def refresh_group(self) -> None:
        """Update the gamemode group status and the join button."""
        if not group_exists():
            self.add_group_button.set_sensitive(False)
            self.group_status.set_text(tr("step.restart.group_missing"))
        elif user_in_group():
            self.add_group_button.set_sensitive(False)
            self.group_status.set_text(tr("step.restart.group_in"))
        else:
            self.add_group_button.set_sensitive(True)
            self.group_status.set_text(tr("step.restart.group_out"))


def build_page(window):
    """Factory used by the general UI while gathering the section pages."""
    return DaemonPage(window)
