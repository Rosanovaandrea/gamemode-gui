"""Core of the CPU section: state, options and INI (de)serialisation.

Self-contained section for the ``[cpu]`` keys. The available cores shown by the
pinning control come from the kernel; the chosen value lives in this section.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional

from spec import OptionSpec

SECTION_ID = "cpu"

CPU_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="pin_cores", type="cores", default=[],
        special=True, special_source="cpu_cores",
        description_id="opt.cpu.pin_cores",
        comment="; Pin the game to a specific list of cores (comma separated, "
                "\"-\" for ranges).\n; Leave empty to let GameMode auto-detect the "
                "cores to use."),
    OptionSpec(
        key="park_cores", type="bool", default=False,
        description_id="opt.cpu.park_cores",
        comment="; Park (offline) all cores except the ones used by the game.\n"
                "; Requires the user to be in the 'gamemode' group."),
]

_CPU_ONLINE_FILE = "/sys/devices/system/cpu/online"


def expand_cpu_list(text: str) -> List[int]:
    """Expand a Linux cpu-list (e.g. ``"0-3,8"``) into a sorted list of ints."""
    cores: List[int] = []
    for token in str(text).split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, _, end = token.partition("-")
            try:
                cores.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                cores.append(int(token))
            except ValueError:
                pass
    return sorted(set(cores))


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


class CpuState:
    """Values chosen by the user for the ``[cpu]`` section."""

    def __init__(self) -> None:
        for spec in CPU_OPTIONS:
            setattr(self, spec.key, spec.default)


class CpuCore:
    """State and logic of the ``[cpu]`` section."""

    section_id = SECTION_ID
    options = CPU_OPTIONS

    def __init__(self) -> None:
        """Create the section state and install the speaking option accessors."""
        self.state = CpuState()
        self._listeners: List[Callable[[str], None]] = []
        self._install_accessors()

    def subscribe(self, listener: Callable[[str], None]) -> None:
        """Register a view callback; it receives the option key that changed."""
        self._listeners.append(listener)

    def _notify(self, changed_key: str) -> None:
        """Notify every subscribed view that one option changed."""
        for listener in self._listeners:
            listener(changed_key)

    def _install_accessors(self) -> None:
        """Create a speaking ``get_<key>`` and ``set_<key>`` for every option."""
        for spec in self.options:
            setattr(self, f"get_{spec.key}", self._make_getter(spec.key))
            setattr(self, f"set_{spec.key}", self._make_setter(spec.key))

    def _make_getter(self, key: str):
        """Return the ``get_<key>`` closure that reads one option from the state."""
        def get_option_value():
            return getattr(self.state, key)
        get_option_value.__name__ = f"get_{key}"
        return get_option_value

    def _make_setter(self, key: str):
        """Return the ``set_<key>`` closure that writes one option and notifies."""
        def set_option_value(value) -> None:
            setattr(self.state, key, value)
            self._notify(key)
        set_option_value.__name__ = f"set_{key}"
        return set_option_value

    def choices_for(self, spec: OptionSpec) -> List[str]:
        """Allowed values of an option: the online cores if special, else static."""
        if spec.special and spec.special_source == "cpu_cores":
            return available_cores()
        return list(spec.choices or [])

    @staticmethod
    def _is_written(spec: OptionSpec, value) -> bool:
        """True if the option is active (a non-empty core list, or a set switch)."""
        if spec.type == "bool":
            return bool(value) != bool(spec.default)
        return bool(value)

    def is_active(self, spec: OptionSpec) -> bool:
        """True if an option is active; used to gate the dependent options."""
        return self._is_written(spec, getattr(self.state, spec.key))

    def reset(self) -> None:
        """Reset every option of this section to its default value."""
        for spec in self.options:
            setattr(self.state, spec.key, spec.default)

    def render(self) -> str:
        """Render the ``[cpu]`` section, only with active options."""
        lines: List[str] = []
        for spec in self.options:
            value = getattr(self.state, spec.key)
            # Skip options still at their default: only active ones are written.
            if not self._is_written(spec, value):
                continue
            # Emit the definition comment above the option, when there is one.
            if spec.comment:
                lines.append(spec.comment)
            # A core list is written as a comma-separated list; a switch as 1/0.
            if spec.type == "cores":
                lines.append(spec.template.format(
                    value=",".join(str(core) for core in value)))
            elif spec.type == "bool":
                lines.append(spec.template.format(value=1 if value else 0))
            else:
                lines.append(spec.template.format(value=value))
        if not lines:
            return ""
        # Wrap the active lines in the section header; the file ends with "\n".
        return f"[{self.section_id}]\n" + "\n".join(lines) + "\n"

    def apply(self, section: Dict[str, List[str]]) -> None:
        """Apply the parsed ``[cpu]`` values (``key -> [raw values]``)."""
        for spec in self.options:
            raw_values = section.get(spec.key)
            if not raw_values:
                continue
            value: Optional[object]
            if spec.type == "cores":
                value = expand_cpu_list(",".join(raw_values))
            elif spec.type == "bool":
                raw = raw_values[-1]
                value = raw.strip() not in ("0", "false", "no")
            else:
                value = raw_values[-1]
            setattr(self.state, spec.key, value)

    def apply_values(self, values: Dict[str, object]) -> None:
        """Set typed values (e.g. from the saved session) for this section."""
        for spec in self.options:
            full_key = f"{self.section_id}.{spec.key}"
            if full_key in values:
                setattr(self.state, spec.key, values[full_key])
