"""Modal dialogs: confirmations, errors, and command output viewers."""

from __future__ import annotations

from typing import List, Optional

from gi.repository import Adw, Gtk


def _dialog(parent: Gtk.Widget, heading: str, body: str,
            responses: List[str], default: Optional[str] = None,
            appearance: str = "suggested") -> Adw.MessageDialog:
    dlg = Adw.MessageDialog(transient_for=parent)
    dlg.set_heading(heading)
    dlg.set_body(body)
    for resp in responses:
        dlg.add_response(resp, resp)
    if default:
        dlg.set_default_response(default)
    dlg.set_response_appearance(default or (responses[0] if responses else ""), appearance)
    return dlg


def confirm(parent, heading: str, body: str, confirm_label: str = "Conferma"):
    """Ask for a yes/no confirmation. Yields True if the user confirms."""
    return _dialog(
        parent, heading, body,
        responses=[confirm_label, "Annulla"],
        default="Annulla",
    )


def info(parent, heading: str, body: str, close_label: str = "OK"):
    return _dialog(parent, heading, body, responses=[close_label], default=close_label)


def error(parent, heading: str, body: str, retry_label: str = "Riprova"):
    return _dialog(
        parent, heading, body,
        responses=[retry_label, "Chiudi"],
        default="Chiudi",
        appearance="destructive" if not retry_label else "suggested",
    )


def command_output(parent, heading: str, output: str, success: bool):
    """Dialog showing the stdout/stderr of a run command with a status icon."""
    dlg = Adw.MessageDialog(transient_for=parent)
    dlg.set_heading(heading)
    if success:
        dlg.set_body("Comando completato con successo.")
    elif not output:
        dlg.set_body("Il comando è fallito (consultare i dettagli).")
    else:
        dlg.set_body("Il comando ha prodotto del testo da consultare.")

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    scroller.set_size_request(-1, 220)
    view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    buf = view.get_buffer()
    buf.set_text(output or "(nessun output)")
    scroller.set_child(view)
    box.append(scroller)
    dlg.set_extra_child(box)

    dlg.add_response("Chiudi", "Chiudi")
    dlg.set_default_response("Chiudi")
    return dlg