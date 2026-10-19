"""Core of the GPU section."""

from __future__ import annotations

from typing import Dict, List

from sections.core import SectionCore
from sections.gpu.options import GPU_OPTIONS
from sections.serialization import (
    parse_into, render_section, written_default,
)
from spec import OptionSpec

SECTION_ID = "gpu"


class GpuCore(SectionCore):
    """State and logic of the ``[gpu]`` section."""

    section_id = SECTION_ID
    options = GPU_OPTIONS

    def is_option_active(self, option: OptionSpec) -> bool:
        return written_default(option, getattr(self.state, option.key))

    def render_ini_section(self) -> str:
        return render_section(self, written=written_default, gate_dependencies=True)

    def apply_parsed_section(self, parsed_section: Dict[str, List[str]]) -> None:
        parse_into(self, parsed_section)
