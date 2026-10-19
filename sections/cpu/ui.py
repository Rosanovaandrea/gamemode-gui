"""View of the CPU section."""

from __future__ import annotations

from ui.pages import SectionPage

TAB_TITLE_ID = "tab.cpu"
TITLE_ID = "step.cpu.title"
SUBTITLE_ID = "step.cpu.subtitle"


class CpuPage(SectionPage):
    """Page with all the ``[cpu]`` options."""

    def __init__(self, core) -> None:
        super().__init__(core, TITLE_ID, SUBTITLE_ID)


def build_page(core):
    return CpuPage(core)
