"""Core of the CPU section."""

from __future__ import annotations

import os
from typing import List

from sections.core import SectionCore
from sections.cpu.options import CPU_OPTIONS
from sections.serialization import (
    cpu_value, expand_cpu_list, written_nonempty,
)
from spec import OptionSpec

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
    written_rule = staticmethod(written_nonempty)
    render_value = staticmethod(cpu_value)

    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        if option.special and option.special_source == "cpu_cores":
            return available_cores()
        return list(option.choices or [])
