"""Integration smoke test.

Creates the real window (requires a DISPLAY), navigates all steps, renders a
config, and saves it to an isolated XDG_CONFIG_HOME so the user's real
configuration is never touched.
"""

import os
import sys
import tempfile

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk

# Isolated config/home.
tmp = tempfile.mkdtemp(prefix="gamemodegui_test_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.environ["HOME"] = os.path.join(tmp, "home")
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.window import GameModeWindow, resolve_config_path  # noqa: E402

results = []
app = None


def _find_option_page(widget):
    """Walk the wrapped box to find the inner _OptionPage with .rows."""
    from ui.steps import _OptionPage
    if isinstance(widget, _OptionPage):
        return widget
    child = widget.get_first_child()
    while child is not None:
        found = _find_option_page(child)
        if found is not None:
            return found
        child = child.get_next_sibling()
    return None


def exercise():
    global app
    app = Gtk.Application.new("io.github.gamemodegui.smoke", 0)
    win = GameModeWindow(app)
    win.present()

    results.append(("window_created", True))
    results.append(("config_path", resolve_config_path()))

    # Navigate through all steps
    for _ in range(4):
        win._navigate(1)
    results.append(("current_step_after_nav", win._current))

    # Exercise an edit on a spin row so the value propagates to the controller
    general_page = _find_option_page(win._general_page)
    first = general_page.rows[0]
    first.set_include(True)
    first.set_value(10)
    results.append(("row_value", first.get_value()))
    results.append(("controller_value", win.controller.get_value(first.spec.id)))

    # Render a config (the edited option must appear)
    txt = win.controller.render()
    results.append(("render_has_reaper", "reaper_freq=10" in txt))

    # Exercise an edit on a spin row so the value propagates to the controller
    # (the wrapped page exposes OptionRow instances on its inner page).
    general_page = _find_option_page(win._general_page)
    first = general_page.rows[0]
    first.set_include(True)
    first.set_value(10)
    results.append(("row_value", first.get_value()))
    results.append(("controller_value", win.controller.get_value(first.spec.id)))

    # Mark dirty and save
    win._mark_dirty()
    results.append(("dirty", win._dirty))
    win.do_save()
    created = os.path.isfile(win.config_path)
    results.append(("file_created", created))
    if created:
        with open(win.config_path) as fh:
            content = fh.read()
        results.append(("file_head", content.splitlines()[0] if content else ""))
        results.append(("file_has_reaper_value", "reaper_freq=10" in content))
        results.append(("orig_created", os.path.isfile(win.cm.orig_path)))

    win.close()
    app.quit()
    return False


def on_activate(_app):
    GLib.idle_add(exercise)


def main():
    Gtk.init_check()
    GLib.timeout_add(6000, lambda: (_ for _ in ()).throw(
        SystemExit("→ timeout")))
    GLib.idle_add(exercise)
    # We don't need a real application loop; drive timers directly.
    ctx = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + 5_000_000
    while GLib.get_monotonic_time() < deadline:
        while ctx.pending():
            ctx.iteration(False)
    for r in results:
        print("RESULT:", r)


if __name__ == "__main__":
    main()