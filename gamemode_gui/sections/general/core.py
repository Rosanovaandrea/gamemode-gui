"""Core of the General section."""

from __future__ import annotations

import glob
from typing import Dict, List

from gamemode_gui.sections.core import SectionCore
from gamemode_gui.sections.general.options import GENERAL_OPTIONS
from gamemode_gui.sections.serialization import (
    bool_value, parse_into, render_section, written_default,
)
from gamemode_gui.spec import OptionSpec

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
            continue
    return governors or list(_FALLBACK_GOVERNORS)


class GeneralCore(SectionCore):
    """State and logic of the ``[general]`` section."""

    section_id = SECTION_ID
    options = GENERAL_OPTIONS

    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        if option.special and option.special_source == "cpu_governors":
            return available_governors()
        return list(option.choices or [])

    def render_ini_section(self) -> str:
        return render_section(self, written=written_default, render_value=bool_value)

    def is_option_active(self, option: OptionSpec) -> bool:
        return written_default(option, getattr(self.state, option.key))

    def apply_parsed_section(self, parsed_section: Dict[str, List[str]]) -> None:
        parse_into(self, parsed_section)
