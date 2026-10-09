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
# Nessuna base installata: il test resta ermetico (non legge /usr/share reale).
os.environ["GAMEMODE_BASE"] = ""
os.environ["HOME"] = os.path.join(tmp, "home")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import GameModeWindow, resolve_config_path, install_app_css  # noqa: E402

results = []


def exercise(*_):
    app = Gtk.Application.new("io.github.gamemodegui.smoke", 0)
    win = GameModeWindow(app)
    win.present()

    results.append(("window_created", True))
    results.append(("app_css_registered", install_app_css()))
    results.append(("config_path", resolve_config_path()))
    results.append(("tabs_count", win.stack.get_pages().get_n_items()))
    results.append(("default_tab", win.stack.get_visible_child_name()))
    results.append(("presentation_default",
                    win.stack.get_visible_child_name() == "presentation"))
    results.append(("presentation_blocks",
                    len(win.presentation_tab.presentation.blocks)))

    # modifica un'opzione nella scheda Generale (nessun "Includi" da attivare)
    first = win.general_tab.rows[0]
    results.append(("stepper_button_styled",
                    "stepper-button" in first._input.minus.get_css_classes()
                    and "stepper-button" in first._input.plus.get_css_classes()))
    first.set_value(10)
    results.append(("controller_value", win.controller.get_value(first.spec.id)))
    results.append(("render_has_reaper", "reaper_freq=10" in win.controller.render()))
    results.append(("dirty_after_edit", win._dirty))

    win.do_save()
    created = os.path.isfile(win.config_path)
    results.append(("file_created", created))
    if created:
        with open(win.config_path) as fh:
            content = fh.read()
        results.append(("file_has_reaper_value", "reaper_freq=10" in content))
        # I default NON vengono piu' scritti: il file contiene solo le attive.
        results.append(("file_hides_defaults", "renice" not in content))
        results.append(("file_hides_idle_gpu", "[gpu]" not in content))
        results.append(("orig_created", os.path.isfile(win.cm.orig_path)))
        results.append(("session_created", os.path.isfile(win.cm.config_path + ".session.json")))

    results.append(("dirty_after_save", win._dirty))

    # --- interruttore power plan GPU ---------------------------------------
    master = win.gpu_tab.rows[0]
    sub = win.gpu_tab.rows[1]
    results.append(("gpu_master_key", master.spec.key))
    results.append(("gpu_sub_disabled_when_off", not sub.get_sensitive()))
    master.set_value("accept-responsibility")
    results.append(("gpu_master_value", win.controller.get_value(master.spec.id)))
    results.append(("gpu_sub_enabled_when_on", sub.get_sensitive()))
    sub.set_value(2)

    # --- ioprio: scelta a pulsanti con valori speciali ----------------------
    ioprio_row = next(r for r in win.general_tab.rows if r.spec.key == "ioprio")
    ioprio_labels = [b.get_label() for b in ioprio_row._input._buttons]
    results.append(("ioprio_buttons", "off" in ioprio_labels and "reset" in ioprio_labels))
    results.append(("choice_button_styled",
                    all("choice-button" in b.get_css_classes()
                        for b in ioprio_row._input._buttons)))
    ioprio_row.set_value("reset")
    results.append(("ioprio_reset_value", win.controller.get_value("general.ioprio")))
    results.append(("render_ioprio_reset", "ioprio=reset" in win.controller.render()))
    ioprio_row.set_value("6")
    results.append(("ioprio_six_value", win.controller.get_value("general.ioprio")))

    # --- CPU: pinning (checkbox core) + parking (switch) --------------------
    cpu_pin = next(r for r in win.cpu_tab.rows if r.spec.key == "pin_cores")
    cpu_park = next(r for r in win.cpu_tab.rows if r.spec.key == "park_cores")
    results.append(("cpu_pin_checks", len(cpu_pin._input._checks) > 0))
    cpu_pin.set_value([0, 1])
    cpu_park.set_value(True)
    results.append(("cpu_pin_value", win.controller.get_value("cpu.pin_cores")))
    results.append(("cpu_park_value", win.controller.get_value("cpu.park_cores")))

    # --- Custom: liste start/end + timeout ---------------------------------
    start_row = next(r for r in win.custom_tab.rows if r.spec.key == "start")
    start_row.set_value(["echo start"])
    results.append(("custom_start_value", win.controller.get_value("custom.start")))

    # --- Custom: toggle notifiche (card in cima) ---------------------------
    notify_start = next(r for r in win.custom_tab.rows
                        if r.spec.key == "notify_start")
    notify_end = next(r for r in win.custom_tab.rows if r.spec.key == "notify_end")
    results.append(("custom_notify_default_off",
                    win.controller.get_value("custom.notify_start") is False))
    notify_start.set_value(True)
    notify_end.set_value(True)
    results.append(("custom_notify_on",
                    win.controller.get_value("custom.notify_start") is True
                    and win.controller.get_value("custom.notify_end") is True))
    results.append(("render_notify_start",
                    'start=notify-send "GameMode started"' in win.controller.render()))
    # La notifica non compare tra gli elementi editabili della lista.
    results.append(("custom_start_excludes_notify",
                    'notify-send' not in " ".join(start_row.get_value())))

    win.do_save()
    with open(win.config_path) as fh:
        content = fh.read()
    results.append(("file_gpu_accept", "apply_gpu_optimisations=accept-responsibility" in content))
    results.append(("file_gpu_device", "gpu_device=2" in content))
    results.append(("file_ioprio", "ioprio=6" in content))
    results.append(("file_pin_cores", "pin_cores=0,1" in content))
    results.append(("file_park_cores", "park_cores=1" in content))
    results.append(("file_custom_start", "start=echo start" in content))
    results.append(("file_notify_start", 'start=notify-send "GameMode started"' in content))
    results.append(("file_notify_end", 'end=notify-send "GameMode ended"' in content))

    # Navigazione a schede: si puo' andare su qualunque scheda.
    win.stack.set_visible_child_name("daemon")
    results.append(("switch_to_daemon", win.stack.get_visible_child_name()))
    win.daemon_tab.append_console("prova console")
    cbuf = win.daemon_tab._console_buf
    ctext = cbuf.get_text(cbuf.get_start_iter(), cbuf.get_end_iter(), False)
    results.append(("daemon_console", "prova console" in ctext))
    win.daemon_tab.clear_console()
    ctext = cbuf.get_text(cbuf.get_start_iter(), cbuf.get_end_iter(), False)
    results.append(("daemon_console_clear", ctext == ""))
    win.stack.set_visible_child_name("summary")
    results.append(("switch_to_summary", win.stack.get_visible_child_name()))

    # Una nuova modifica torna "dirty".
    first.set_value(20)
    results.append(("dirty_again", win._dirty))
    results.append(("value_after_edit", win.controller.get_value(first.spec.id)))
    results.append(("row_value_matches", win.general_tab.rows[0].get_value()))

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