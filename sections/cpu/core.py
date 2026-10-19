"""Core of the CPU section."""

from __future__ import annotations

import os
from typing import Dict, List

from sections.core import SectionCore
from sections.cpu.options import CPU_OPTIONS
from sections.serialization import (
    cpu_value, parse_into, render_section, written_nonempty,
)
from spec import OptionSpec
from utils import expand_cpu_list

SECTION_ID = "cpu"
_CPU_ONLINE_FILE = "/sys/devices/system/cpu/online"


def available_cores() -> List[str]:
    """Online core ids as strings (with an ``os.cpu_count`` fallback)."""
    try:
        with open(_CPU_ONLINE_FILE, "r", encoding="utf-8") as handle:
            cores = expand_cpu_list(handle.read().strip())
        if cores:
            return [str(core) for core in cores]
    except OSError:
        pass
    return [str(core) for core in range(os.cpu_count() or 1)]


class CpuCore(SectionCore):
    """State and logic of the ``[cpu]`` section."""

    section_id = SECTION_ID
    options = CPU_OPTIONS

    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        if option.special and option.special_source == "cpu_cores":
            return available_cores()
        return list(option.choices or [])

    def is_option_active(self, option: OptionSpec) -> bool:
        return written_nonempty(option, getattr(self.state, option.key))

    def render_ini_section(self) -> str:
        return render_section(self, written=written_nonempty, render_value=cpu_value)

    def apply_parsed_section(self, parsed_section: Dict[str, List[str]]) -> None:
        parse_into(self, parsed_section)
