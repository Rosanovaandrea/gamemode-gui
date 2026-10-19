"""View of the General section."""

from __future__ import annotations

from ui.pages import SectionPage

TAB_TITLE_ID = "tab.general"
TITLE_ID = "step.general.title"
SUBTITLE_ID = "step.general.subtitle"


class GeneralPage(SectionPage):
    """Page with all the ``[general]`` options."""

    def __init__(self, core) -> None:
        super().__init__(core, TITLE_ID, SUBTITLE_ID)


def build_page(core):
    return GeneralPage(core)
