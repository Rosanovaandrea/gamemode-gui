"""Step page builders.

Builds the per-section forms, the summary/preview page and the final
restart page. Each step reads/writes through the :class:`SessionController`.
"""

from __future__ import annotations

from gi.repository import Adw, Gtk

from core.gamemode_utils import (
    add_user_to_group,
    group_exists,
    user_in_group,
)
from core.options_table import options_for_section
from ui.controller import SessionController
from ui.widgets import OptionRow


class _OptionPage(Gtk.Box):
    """Scrollable form of rows for a given section."""

    def __init__(self, controller: SessionController, section: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self.section = section
        self.rows = []

        scroller = Gtk.ScrolledWindow(vexpand=True)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        scroller.set_child(listbox)

        for spec in options_for_section(section):
            row = self._make_row(spec)
            self.rows.append(row)
            listbox.append(row)

        self.append(scroller)

    def _make_row(self, spec):
        def on_change(spec_id):
            self.controller.set_include(spec_id, row.get_include())
            if row.get_include():
                self.controller.set_option(spec_id, row.get_value())

        row = OptionRow(spec, on_change=on_change)
        # initial from controller (suppress dirty-marking during setup)
        row._suppress = True
        row.set_value(self.controller.get_value(spec.id))
        row.set_include(self.controller.is_active(spec.id))
        row._suppress = False
        return row

    def refresh(self) -> None:
        for row in self.rows:
            row.set_value(self.controller.get_value(row.spec.id))
            row.set_include(self.controller.is_active(row.spec.id))


def build_general_step(controller) -> Gtk.Widget:
    page = _OptionPage(controller, "general")
    return _wrap_with_title(page, "Generale",
                            "Impostazioni principali di GameMode.")


def build_filter_step(controller) -> Gtk.Widget:
    page = _OptionPage(controller, "filter")
    return _wrap_with_title(page, "Filtro",
                            "Whitelist e blacklist dei programmi.")


def build_gpu_step(controller) -> Gtk.Widget:
    page = _OptionPage(controller, "gpu")

    # Safety banner
    banner = Adw.Banner(
        title="Attenzione: le ottimizzazioni [gpu] non hanno effetto se il "
              "file si trova in $PWD o $XDG_CONFIG_HOME. Vengono applicate "
              "solo da /etc/gamemode.ini. Usale a tuo rischio."
    )
    banner.add_css_class("error")
    page.prepend(banner)

    return _wrap_with_title(page, "GPU",
                            "Ottimizzazioni hardware (NVIDIA / AMD).")


def _wrap_with_title(page, title: str, subtitle: str) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    header = Adw.Clamp()
    head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    t = Gtk.Label(label=title, xalign=0.0, css_classes=["title-2"])
    s = Gtk.Label(label=subtitle, xalign=0.0, css_classes=["dim-label"], wrap=True)
    head.append(t)
    head.append(s)
    header.set_child(head)
    box.append(header)
    box.append(page)
    return box


def build_summary_step(controller, actions) -> Gtk.Widget:
    """Step 4: preview + save + backup/restore actions.

    ``actions`` is an object exposing: do_save(), do_restore_backup(),
    do_restore_orig(), do_add_group().
    """
    # Build manually: preview + buttons
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    t = Gtk.Label(label="Riepilogo e conferma", xalign=0.0, css_classes=["title-2"])
    s = Gtk.Label(label="Anteprima del file che verrà scritto.",
                  xalign=0.0, css_classes=["dim-label"])
    box.append(t)
    box.append(s)

    scroller = Gtk.ScrolledWindow(vexpand=True)
    view = Gtk.TextView(editable=False, monospace=True,
                        wrap_mode=Gtk.WrapMode.WORD_CHAR)
    buf = view.get_buffer()
    buf.set_text(controller.render())
    scroller.set_child(view)
    box.append(scroller)

    def _refresh() -> None:
        buf.set_text(controller.render())

    box._refresh_summary = _refresh

    btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    save_btn = Gtk.Button(label="Salva")
    save_btn.add_css_class("suggested-action")
    save_btn.connect("clicked", lambda *_: actions.do_save())
    rest_bak = Gtk.Button(label="Ripristina backup precedente")
    rest_bak.connect("clicked", lambda *_: actions.do_restore_backup())
    rest_orig = Gtk.Button(label="Ripristina originale")
    rest_orig.connect("clicked", lambda *_: actions.do_restore_orig())
    btn_row.append(save_btn)
    btn_row.append(rest_bak)
    btn_row.append(rest_orig)
    box.append(btn_row)

    return box


def build_restart_step(controller, actions) -> Gtk.Widget:
    """Step 5: final confirmation + optional daemon restart."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)

    icon = Gtk.Image(icon_name="emblem-ok-symbolic", pixel_size=48)
    box.append(icon)
    t = Gtk.Label(label="Configurazione salvata", css_classes=["title-1"])
    box.append(t)
    s = Gtk.Label(
        label="La configurazione è stata scritta correttamente. Puoi riavviare "
              "il daemon GameMode ora oppure chiudere.",
        wrap=True, justify=Gtk.Justification.CENTER,
    )
    box.append(s)

    group_status = Gtk.Label(label="", css_classes=["dim-label"], wrap=True)
    group_status.set_halign(Gtk.Align.CENTER)
    box.append(group_status)

    btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    restart_btn = Gtk.Button(label="Riavvia gamemoded")
    restart_btn.add_css_class("suggested-action")
    restart_btn.connect("clicked", lambda *_: actions.do_restart_daemon())
    close_btn = Gtk.Button(label="Chiudi")
    add_group_btn = Gtk.Button(label="Aggiungi al gruppo gamemode")
    btn_row.append(restart_btn)
    btn_row.append(close_btn)
    box.append(btn_row)
    box.append(add_group_btn)

    def _refresh_group(*_):
        if not group_exists():
            add_group_btn.set_sensitive(False)
            group_status.set_text("Il gruppo 'gamemode' non esiste su questo sistema.")
        elif user_in_group():
            add_group_btn.set_sensitive(False)
            group_status.set_text("Sei già nel gruppo 'gamemode'.")
        else:
            add_group_btn.set_sensitive(True)
            group_status.set_text(
                "Non risulti ancora nel gruppo 'gamemode'. Dopo l'aggiunta è "
                "necessario il logout/login perché abbia effetto."
            )

    add_group_btn.connect("clicked", lambda *_: actions.do_add_group(_refresh_group))
    box._refresh_group = _refresh_group
    box._refresh_group()
    return box