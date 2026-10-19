"""View of the Presentation section (stateless, data-driven)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from i18n.translator import tr
from sections.presentation import core


class PresentationPage(Adw.PreferencesPage):
    """Introductory page: what GameMode is, how to use it, warnings."""

    def __init__(self) -> None:
        super().__init__()
        presentation = core.PRESENTATION
        self.add(Adw.PreferencesGroup(
            title=tr(presentation.title_id),
            description=tr(presentation.subtitle_id),
        ))
        for block in presentation.blocks:
            group = Adw.PreferencesGroup(
                title=tr(block.heading_id),
                description=tr(block.body_id),
            )
            if block.warning:
                group.set_header_suffix(
                    Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
            self.add(group)


def build_page(window):
    """Factory used by the general UI while gathering the section pages."""
    return PresentationPage()
