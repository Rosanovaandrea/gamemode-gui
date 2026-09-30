"""Application entry point for the GameMode GUI."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from ui import steps  # noqa: F401  (ensures module imports cleanly)
from ui.window import GameModeWindow


class GameModeApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.gamemodegui.GameModeGui",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._window: Adw.ApplicationWindow | None = None

    def do_activate(self) -> None:
        if self._window is None:
            self._window = GameModeWindow(application=self)
        self._window.present()


def main() -> int:
    app = GameModeApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())