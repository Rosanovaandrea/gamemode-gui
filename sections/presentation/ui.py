"""View of the Presentation section (stateless, data-driven).

Shows the blocks loaded by :mod:`sections.presentation.core`; a
block marked as a warning is rendered as a card with a warning icon.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from i18n import tr
from sections.presentation import core
from ui.widgets import PageHeader


class PresentationPage(Gtk.Box):
    """Introductory page: what GameMode is, how to use it, warnings."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add_css_class("presentation-page")
        presentation = core.PRESENTATION
        self.append(PageHeader(presentation.title_id, presentation.subtitle_id))

        scroller = Gtk.ScrolledWindow(vexpand=True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.add_css_class("presentation-content")
        for block in presentation.blocks:
            content.append(_presentation_block(block))
        scroller.set_child(content)
        self.append(scroller)


def _presentation_block(block) -> Gtk.Widget:
    """A Presentation block: heading + body, card with icon if a warning."""
    heading = Gtk.Label(label=tr(block.heading_id), xalign=0.0, wrap=True,
                        css_classes=["heading"])
    body = Gtk.Label(label=tr(block.body_id), xalign=0.0, wrap=True, selectable=True)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    if not block.warning:
        box.append(heading)
        box.append(body)
        return box

    box.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    inner.add_css_class("presentation-warning")
    icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
    icon.set_valign(Gtk.Align.START)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    text.set_hexpand(True)
    text.append(heading)
    text.append(body)
    inner.append(icon)
    inner.append(text)
    box.append(inner)
    return box


def build_page(window):
    """Factory used by the general UI while gathering the section pages."""
    return PresentationPage()
