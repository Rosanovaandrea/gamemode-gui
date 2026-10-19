"""Core of the CPU section: state and INI (de)serialisation.

Self-contained section for the ``[cpu]`` keys; the options live in
:mod:`sections.cpu.options` and the shared core machinery is in
:mod:`sections.core`. The available cores shown by the pinning control come from
the kernel; the chosen value lives in this section.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from sections.core import SectionCore
from sections.cpu.options import CPU_OPTIONS
from spec import OptionSpec
from gamemode_gui.utils import expand_cpu_list

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

    # -- allowed values ------------------------------------------------------
    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        """Allowed values of an option: the online cores if special, else static."""
        if option.special and option.special_source == "cpu_cores":
            return available_cores()
        return list(option.choices or [])

    # -- rendering -----------------------------------------------------------
    @staticmethod
    def _is_option_written(option: OptionSpec, value) -> bool:
        """True if the option is active (a non-empty core list, or a set switch)."""
        if option.type == "bool":
            return bool(value) != bool(option.default)
        return bool(value)

    def is_option_active(self, option: OptionSpec) -> bool:
        """True if an option is active; used to gate the dependent options."""
        return self._is_option_written(option, getattr(self.state, option.key))

    def render_ini_section(self) -> str:
        """Render the ``[cpu]`` section, only with active options."""
        rendered_lines: List[str] = []
        for option in self.options:
            value = getattr(self.state, option.key)
            # Skip options still at their default: only active ones are written.
            if not self._is_option_written(option, value):
                continue
            # Emit the definition comment above the option, when there is one.
            if option.comment:
                rendered_lines.append(option.comment)
            # A core list is written as a comma-separated list; a switch as 1/0.
            if option.type == "cores":
                selected_cores = ",".join(str(core) for core in value)
                rendered_lines.append(option.template.format(value=selected_cores))
            elif option.type == "bool":
                rendered_lines.append(option.template.format(value=1 if value else 0))
            else:
                rendered_lines.append(option.template.format(value=value))
        if not rendered_lines:
            return ""
        # Wrap the active lines in the section header; the file ends with "\n".
        return f"[{self.section_id}]\n" + "\n".join(rendered_lines) + "\n"

    # -- reading -------------------------------------------------------------
    def apply_parsed_section(self, parsed_section: Dict[str, List[str]]) -> None:
        """Apply the parsed ``[cpu]`` values (``key -> [raw values]``)."""
        for option in self.options:
            raw_option_values = parsed_section.get(option.key)
            if not raw_option_values:
                continue
            value: Optional[object]
            if option.type == "cores":
                value = expand_cpu_list(",".join(raw_option_values))
            elif option.type == "bool":
                raw_value = raw_option_values[-1]
                value = raw_value.strip() not in ("0", "false", "no")
            else:
                value = raw_option_values[-1]
            setattr(self.state, option.key, value)
