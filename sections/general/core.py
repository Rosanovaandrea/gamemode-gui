"""Core of the General section: state, options and INI (de)serialisation.

This section is self-contained: it defines its own options (the ``[general]``
keys), owns its own state, and knows how to render itself to, and read itself
from, gamemode.ini. The only shared pieces are the option descriptor and the
widget kit (views) plus i18n.
"""

from __future__ import annotations

import glob
from typing import Callable, Dict, List, Optional

from spec import OptionSpec

SECTION_ID = "general"

# --- the options of the [general] section (single source of truth for it) ---

GENERAL_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="reaper_freq", type="int", default=5, min_value=1,
        description_id="opt.general.reaper_freq",
        comment="; The reaper thread will check every 5 seconds for exited clients, "
                "for config file changes, and for the CPU/iGPU power balance"),
    OptionSpec(
        key="desiredgov", type="choice", default="performance",
        special=True, special_source="cpu_governors",
        description_id="opt.general.desiredgov",
        comment="; The desired governor is used when entering GameMode instead "
                "of \"performance\""),
    OptionSpec(
        key="defaultgov", type="choice", default="",
        special=True, special_source="cpu_governors",
        description_id="opt.general.defaultgov",
        comment="; The default governor is used when leaving GameMode instead of "
                "restoring the original value"),
    OptionSpec(
        key="desiredprof", type="choice", default="performance",
        choices=["performance", "low-power", "balanced"],
        description_id="opt.general.desiredprof",
        comment="; The desired platform profile is used when entering GameMode "
                "instead of \"performance\""),
    OptionSpec(
        key="defaultprof", type="choice", default="",
        choices=["performance", "low-power", "balanced"],
        description_id="opt.general.defaultprof",
        comment="; The default platform profile is used when leaving GameMode "
                "instead of restoring the original value"),
    OptionSpec(
        key="igpu_desiredgov", type="choice", default="powersave",
        special=True, special_source="cpu_governors",
        description_id="opt.general.igpu_desiredgov",
        comment="; The iGPU desired governor is used when the integrated GPU is "
                "under heavy load"),
    OptionSpec(
        key="igpu_power_threshold", type="float", default=0.3,
        min_value=-1.0, max_value=1.0,
        description_id="opt.general.igpu_power_threshold",
        comment="; Threshold to use to decide when the integrated GPU is under "
                "heavy load"),
    OptionSpec(
        key="softrealtime", type="choice", default="off",
        choices=["auto", "on", "off"],
        description_id="opt.general.softrealtime",
        comment="; GameMode can change the scheduler policy to SCHED_ISO on "
                "kernels which support it"),
    OptionSpec(
        key="renice", type="int", default=0, min_value=0, max_value=20,
        description_id="opt.general.renice",
        comment="; GameMode can renice game processes. You can put any value "
                "between 0 and 20 here"),
    OptionSpec(
        key="ioprio", type="choice", default="0",
        choices=["0", "1", "2", "3", "4", "5", "6", "7", "off", "reset"],
        description_id="opt.general.ioprio",
        comment="; By default, GameMode adjusts the iopriority of clients to BE/0"),
    OptionSpec(
        key="inhibit_screensaver", type="bool", default=True,
        description_id="opt.general.inhibit_screensaver",
        comment="; Sets whether gamemode will inhibit the screensaver when active"),
    OptionSpec(
        key="disable_splitlock", type="bool", default=True,
        description_id="opt.general.disable_splitlock",
        comment="; Sets whether gamemode will disable split lock mitigation when active"),
]

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


class GeneralState:
    """Values chosen by the user for the ``[general]`` section."""

    def __init__(self) -> None:
        for spec in GENERAL_OPTIONS:
            setattr(self, spec.key, spec.default)


class GeneralCore:
    """State and logic of the ``[general]`` section."""

    section_id = SECTION_ID
    options = GENERAL_OPTIONS

    def __init__(self) -> None:
        self.state = GeneralState()
        self._listeners: List[Callable[[str], None]] = []
        self._install_accessors()

    # -- change notification (React-like) ------------------------------------
    def subscribe(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def _notify(self, changed_key: str) -> None:
        for listener in self._listeners:
            listener(changed_key)

    # -- speaking accessors, one per option ----------------------------------
    def _install_accessors(self) -> None:
        for spec in self.options:
            setattr(self, f"get_{spec.key}", self._make_getter(spec.key))
            setattr(self, f"set_{spec.key}", self._make_setter(spec.key))

    def _make_getter(self, key: str):
        def get_option_value():
            return getattr(self.state, key)
        get_option_value.__name__ = f"get_{key}"
        get_option_value.__doc__ = f"Current value of the '{key}' option."
        return get_option_value

    def _make_setter(self, key: str):
        def set_option_value(value) -> None:
            setattr(self.state, key, value)
            self._notify(key)
        set_option_value.__name__ = f"set_{key}"
        set_option_value.__doc__ = f"Set the '{key}' option and notify the views."
        return set_option_value

    # -- allowed values ------------------------------------------------------
    def choices_for(self, spec: OptionSpec) -> List[str]:
        """Allowed values for an option: from the kernel if special, else static."""
        if spec.special and spec.special_source == "cpu_governors":
            return available_governors()
        return list(spec.choices or [])

    # -- rendering -----------------------------------------------------------
    def reset(self) -> None:
        """Reset every option of this section to its default value."""
        for spec in self.options:
            setattr(self.state, spec.key, spec.default)

    def render(self) -> str:
        """Render the ``[general]`` section, only with its active options."""
        lines: List[str] = []
        for spec in self.options:
            value = getattr(self.state, spec.key)
            if not self._is_written(spec, value):
                continue
            if spec.comment:
                lines.append(spec.comment)
            lines.append(self._render_line(spec, value))
        if not lines:
            return ""
        return f"[{self.section_id}]\n" + "\n".join(lines) + "\n"

    @staticmethod
    def _is_written(spec: OptionSpec, value) -> bool:
        """True if the option is active (differs from its default)."""
        if spec.type == "bool":
            return bool(value) != bool(spec.default)
        if value is None or str(value) == "":
            return False
        return str(value) != str(spec.default)

    @staticmethod
    def _render_line(spec: OptionSpec, value) -> str:
        if spec.type == "bool":
            return spec.template.format(value=1 if value else 0)
        return spec.template.format(value=value)

    def is_active(self, spec: OptionSpec) -> bool:
        """True if an option is active, used to gate dependent options."""
        return self._is_written(spec, getattr(self.state, spec.key))

    # -- reading -------------------------------------------------------------
    def apply(self, section: Dict[str, List[str]]) -> None:
        """Apply the parsed ``[general]`` values (``key -> [raw values]``)."""
        for spec in self.options:
            raw_values = section.get(spec.key)
            if not raw_values:
                continue
            value = self._parse_value(spec, raw_values)
            if value is not None:
                setattr(self.state, spec.key, value)

    @staticmethod
    def _parse_value(spec: OptionSpec, raw_values: List[str]) -> Optional[object]:
        raw = raw_values[-1] if len(raw_values) == 1 else ",".join(raw_values)
        try:
            if spec.type == "int":
                return int(raw)
            if spec.type == "float":
                return float(raw)
            if spec.type == "bool":
                return raw.strip() not in ("0", "false", "no")
            return raw
        except ValueError:
            return None

    def apply_values(self, values: Dict[str, object]) -> None:
        """Set typed values (e.g. from the saved session) for this section."""
        for spec in self.options:
            full_key = f"{self.section_id}.{spec.key}"
            if full_key in values:
                setattr(self.state, spec.key, values[full_key])
