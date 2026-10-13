"""Core of the General section: state and INI (de)serialisation.

This section is self-contained: its options (the ``[general]`` keys) live in
:mod:`sections.general.options` and the shared core machinery (state, accessors,
change notification, reset) is in :mod:`sections.core`. This module adds only the
render/read rules of the ``[general]`` block and the kernel governor lookup.
"""

from __future__ import annotations

import glob
from typing import Dict, List, Optional

from sections.core import SectionCore
from sections.general.options import GENERAL_OPTIONS
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
            continue
    return governors or list(_FALLBACK_GOVERNORS)


class GeneralCore(SectionCore):
    """State and logic of the ``[general]`` section."""

    section_id = SECTION_ID
    options = GENERAL_OPTIONS

    # -- allowed values ------------------------------------------------------
    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        """Allowed values for an option: from the kernel if special, else static."""
        if option.special and option.special_source == "cpu_governors":
            return available_governors()
        return list(option.choices or [])

    # -- rendering -----------------------------------------------------------
    def render_ini_section(self) -> str:
        """Render the ``[general]`` section, only with its active options."""
        rendered_lines: List[str] = []
        for option in self.options:
            value = getattr(self.state, option.key)
            # Skip options still at their default: only active ones are written.
            if not self._is_option_written(option, value):
                continue
            # Emit the definition comment above the option, when there is one.
            if option.comment:
                rendered_lines.append(option.comment)
            rendered_lines.append(self._render_option_line(option, value))
        if not rendered_lines:
            return ""
        # Wrap the active lines in the section header; the file ends with "\n".
        return f"[{self.section_id}]\n" + "\n".join(rendered_lines) + "\n"

    @staticmethod
    def _is_option_written(option: OptionSpec, value) -> bool:
        """True if the option is active, i.e. its value differs from the default."""
        if option.type == "bool":
            return bool(value) != bool(option.default)
        if value is None or str(value) == "":
            return False
        return str(value) != str(option.default)

    @staticmethod
    def _render_option_line(option: OptionSpec, value) -> str:
        """Format one option as an INI line (booleans as 1/0, others as-is)."""
        if option.type == "bool":
            return option.template.format(value=1 if value else 0)
        return option.template.format(value=value)

    def is_option_active(self, option: OptionSpec) -> bool:
        """True if an option is active, used to gate dependent options."""
        return self._is_option_written(option, getattr(self.state, option.key))

    # -- reading -------------------------------------------------------------
    def apply_parsed_section(self, parsed_section: Dict[str, List[str]]) -> None:
        """Apply the parsed ``[general]`` values (``key -> [raw values]``)."""
        for option in self.options:
            raw_option_values = parsed_section.get(option.key)
            if not raw_option_values:
                continue
            value = self._parse_option_value(option, raw_option_values)
            if value is not None:
                setattr(self.state, option.key, value)

    @staticmethod
    def _parse_option_value(option: OptionSpec,
                            raw_option_values: List[str]) -> Optional[object]:
        """Convert the raw INI values of one option to its Python type (or None)."""
        raw_value = (raw_option_values[-1] if len(raw_option_values) == 1
                     else ",".join(raw_option_values))
        try:
            if option.type == "int":
                return int(raw_value)
            if option.type == "float":
                return float(raw_value)
            if option.type == "bool":
                return raw_value.strip() not in ("0", "false", "no")
            return raw_value
        except ValueError:
            return None
