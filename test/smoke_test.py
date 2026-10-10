"""Interface smoke test for the refactored package.

Builds the real window (needs a DISPLAY), navigates the tabs, edits an option and
saves to a temporary path (GAMEMODE_CONFIG), so the user's real configuration is
never touched.
"""

import os
import sys
import tempfile

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk

# Isolation: temporary config path + temporary home, no installed base.
_tmp = tempfile.mkdtemp(prefix="gamemodegui_test_")
os.environ["GAMEMODE_CONFIG"] = os.path.join(_tmp, "config", "gamemode.ini")
os.environ["GAMEMODE_BASE"] = ""
os.environ["HOME"] = os.path.join(_tmp, "home")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp, "config")
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)
os.makedirs(os.path.dirname(os.environ["GAMEMODE_CONFIG"]), exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n, initializer, ui  # noqa: E402

results = []


def exercise(*_):
    app = Gtk.Application.new("io.github.gamemodegui.smoke", 0)
    window = ui.MainWindow(initializer.build_app(), application=app)
    window.present()

    results.append(("pages", list(window.pages.keys())))
    results.append(("presentation_page", type(window.pages["presentation"]).__name__))

    # The save / restore actions are global (same bar on every tab).
    labels = []

    def collect_labels(widget):
        label = widget.get_label() if hasattr(widget, "get_label") else None
        if label:
            labels.append(label)
        child = widget.get_first_child()
        while child:
            collect_labels(child)
            child = child.get_next_sibling()

    collect_labels(window._build_action_bar())
    results.append(("global_actions",
                    i18n.tr("btn.restore_backup") in labels
                    and i18n.tr("btn.restore_orig") in labels
                    and i18n.tr("btn.save") in labels))

    general = window.pages["general"]
    results.append(("general_rows", len(general.rows)))
    first = general.rows[0]
    first.set_value(10)
    results.append(("state_after_edit", general.core.get_reaper_freq()))
    results.append(("render_has_reaper", "reaper_freq=10" in window.core.render()))
    results.append(("dirty_after_edit", window._dirty))

    # Kernel-derived choices must be populated (governors / CPU cores).
    governor_row = next(row for row in general.rows if row.spec.key == "desiredgov")
    results.append(("governors_populated", len(governor_row._input._buttons) > 0))
    cpu_page = window.pages["cpu"]
    pin_row = next(row for row in cpu_page.rows if row.spec.key == "pin_cores")
    results.append(("cores_populated", len(pin_row._input._checks) > 0))

    window.do_save()
    created = os.path.isfile(window.config_path)
    results.append(("file_created", created))
    if created:
        content = open(window.config_path, encoding="utf-8").read()
        results.append(("file_has_reaper", "reaper_freq=10" in content))
        results.append(("file_hides_defaults", "renice" not in content and "[gpu]" not in content))
        results.append(("orig_created", os.path.isfile(window.config_path + ".orig")))

    # A reload (as triggered after a restore) resets every section, including
    # values that are not present in the file.
    renice_row = next(row for row in general.rows if row.spec.key == "renice")
    general.core.set_renice(15)
    general.refresh()
    results.append(("ui_before_reload", renice_row.get_value() == 15))
    initializer.reload(window.state)
    window._refresh_all()
    results.append(("ui_after_reload_reset", renice_row.get_value() == 0))

    # GPU master/sub gating.
    gpu = window.pages["gpu"]
    master = next(row for row in gpu.rows if row.spec.key == "apply_gpu_optimisations")
    sub = next(row for row in gpu.rows if row.spec.key == "gpu_device")
    results.append(("gpu_sub_disabled_when_off", not sub.get_sensitive()))
    master.set_value("accept-responsibility")
    results.append(("gpu_master_value", gpu.core.get_apply_gpu_optimisations()))
    results.append(("gpu_sub_enabled_when_on", sub.get_sensitive()))

    # Custom notification toggle + list.
    custom = window.pages["custom"]
    start_row = next(row for row in custom.rows if row.spec.key == "start")
    start_row.set_value(["echo start"])
    notify_row = next(row for row in custom.rows if row.spec.key == "notify_start")
    notify_row.set_value(True)
    results.append(("custom_notify_on", custom.core.get_notify_start() is True))
    results.append(("render_notify",
                    'start=notify-send "GameMode started"' in window.core.render()))

    # Daemon console round-trip.
    daemon = window.pages["daemon"]
    daemon.append_console("console test")
    buffer = daemon._console_buffer
    text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
    results.append(("daemon_console", "console test" in text))
    daemon.clear_console()
    text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
    results.append(("daemon_console_clear", text == ""))

    # Navigation across every tab.
    for name in window.pages:
        window.stack.set_visible_child_name(name)
        results.append((f"navigate_{name}", window.stack.get_visible_child_name() == name))

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
    for result in results:
        print("RESULT:", result)


if __name__ == "__main__":
    main()
