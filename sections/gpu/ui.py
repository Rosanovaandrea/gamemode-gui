"""View of the GPU section."""

from __future__ import annotations

from ui.pages import SectionPage

TAB_TITLE_ID = "tab.gpu"
TITLE_ID = "step.gpu.title"
SUBTITLE_ID = "step.gpu.subtitle"
BANNER_ID = "gpu.banner"


class GpuPage(SectionPage):
    """Page with the ``[gpu]`` options and the hardware warning banner."""

    def __init__(self, core) -> None:
        super().__init__(core, TITLE_ID, SUBTITLE_ID, banner_id=BANNER_ID)


def build_page(core):
    return GpuPage(core)
