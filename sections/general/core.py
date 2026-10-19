"""Core of the General section."""

from __future__ import annotations

import glob
from typing import List

from sections.core import SectionCore
from sections.general.options import GENERAL_OPTIONS
from sections.serialization import bool_value
from spec import OptionSpec

SECTION_ID = "general"
_GOVERNOR_FILES = "/sys/devices/system/cpu/cpu*/cpufreq/scaling_available_governors"
_FALLBACK_GOVERNORS = ["performance", "powersave", "ondemand", "conservative", "schedutil"]


def available_governors() -> List[str]:
    """CPU governors available on the system (static fallback if unreadable)."""
    governors: List[str] = []
    for path in glob.glob(_GOVERNOR_FILES):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for governor in handle.read().split():
                    if governor not in governors:
                        governors.append(governor)
        except OSError:
            pass
    return governors or list(_FALLBACK_GOVERNORS)


class GeneralCore(SectionCore):
    """State and logic of the ``[general]`` section."""

    section_id = SECTION_ID
    options = GENERAL_OPTIONS
    render_value = staticmethod(bool_value)

    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        if option.special and option.special_source == "cpu_governors":
            return available_governors()
        return list(option.choices or [])
