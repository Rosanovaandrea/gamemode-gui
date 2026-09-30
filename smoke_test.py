"""Smoke test dell'interfaccia.

Crea la finestra reale (serve un DISPLAY), naviga tutti gli step, modifica
un'opzione e salva su un percorso temporaneo (GAMEMODE_CONFIG), così la
configurazione reale dell'utente non viene mai toccata.
"""

import os
import sys
import tempfile

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk

# Isolamento: percorso config temporaneo + home temporanea
tmp = tempfile.mkdtemp(prefix="gamemodegui_test_")
os.environ["GAMEMODE_CONFIG"] = os.path.join(tmp, "config", "gamemode.ini")
os.environ["HOME"] = os.path.join(tmp, "home")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import GameModeWindow, resolve_config_path  # noqa: E402

results = []


def exercise(*_):
    app = Gtk.Application.new("io.github.gamemodegui.smoke", 0)
    win = GameModeWindow(app)
    win.present()

    results.append(("window_created", True))
    results.append(("config_path", resolve_config_path()))

    # naviga fino allo step di riepilogo
    for _ in range(4):
        win._navigate(1)
    results.append(("current_step_after_nav", win._current))

    # modifica un'opzione nel passo generale
    first = win.general_step.rows[0]
    first.set_include(True)
    first.set_value(10)
    results.append(("controller_value", win.controller.get_value(first.spec.id)))
    results.append(("render_has_reaper", "reaper_freq=10" in win.controller.render()))

    win._mark_dirty()
    win.do_save()
    created = os.path.isfile(win.config_path)
    results.append(("file_created", created))
    if created:
        with open(win.config_path) as fh:
            content = fh.read()
        results.append(("file_head", content.splitlines()[0]))
        results.append(("file_has_reaper_value", "reaper_freq=10" in content))
        results.append(("orig_created", os.path.isfile(win.cm.orig_path)))
        results.append(("session_created", os.path.isfile(win.cm.config_path + ".session.json")))

    win.close()
    app.quit()
    return False


def main():
    if not Gtk.init_check():
        print("RESULT: no display available")
        return
    GLib.idle_add(exercise)
    ctx = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + 5_000_000
    while GLib.get_monotonic_time() < deadline:
        while ctx.pending():
            ctx.iteration(False)
    for r in results:
        print("RESULT:", r)


if __name__ == "__main__":
    main()