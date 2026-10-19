"""View of the Custom section."""

from __future__ import annotations

from gamemode_gui.ui.pages import SectionPage

TAB_TITLE_ID = "tab.custom"
TITLE_ID = "step.custom.title"
SUBTITLE_ID = "step.custom.subtitle"
TOGGLE_CARD_ID = "custom.notifications.title"


class CustomPage(SectionPage):
    """Page with the notification card and the script list editors."""

    def __init__(self, core) -> None:
        super().__init__(core, TITLE_ID, SUBTITLE_ID,
                         card_title_id=TOGGLE_CARD_ID,
                         card_types=("toggle_entry",),
                         exclude_types=("toggle_entry",))


def build_page(core):
    return CustomPage(core)
