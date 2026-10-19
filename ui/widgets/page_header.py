"""Shared page header: title plus subtitle."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from i18n.translator import tr


class PageHeader(Gtk.Box):
    """Title and subtitle used at the top of every page."""

    def __init__(self, title_id: str, subtitle_id: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(Gtk.Label(label=tr(title_id), xalign=0.0,
                              css_classes=["title-2"]))
        self.append(Gtk.Label(label=tr(subtitle_id), xalign=0.0,
                              css_classes=["dim-label"], wrap=True))
