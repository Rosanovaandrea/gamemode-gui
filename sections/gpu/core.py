"""Core of the GPU section: state, options and INI (de)serialisation.

Self-contained section for the ``[gpu]`` keys. The options other than
``apply_gpu_optimisations`` depend on it, so they are only written (and enabled in
the view) when the master switch is on.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from spec import OptionSpec

SECTION_ID = "gpu"

GPU_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="apply_gpu_optimisations", type="enable", default="0",
        on_value="accept-responsibility", label_id="opt.gpu.enable_power_plan.label",
        description_id="opt.gpu.apply_gpu_optimisations",
        comment="; Warning: Use these settings at your own risk. Any damage to "
                "hardware is your responsibility and yours alone"),
    OptionSpec(
        key="gpu_device", type="int", default=0, min_value=0,
        description_id="opt.gpu.gpu_device", depends_on="apply_gpu_optimisations",
        comment="; The DRM device number on the system (usually 0)"),
    OptionSpec(
        key="nv_powermizer_mode", type="choice", default="", choices=["0", "1", "2"],
        description_id="opt.gpu.nv_powermizer_mode",
        depends_on="apply_gpu_optimisations",
        comment="; Nvidia specific settings\n; Requires the coolbits extension "
                "activated in nvidia-xconfig"),
    OptionSpec(
        key="nv_core_clock_mhz_offset", type="int", default=-1,
        description_id="opt.gpu.nv_core_clock_mhz_offset",
        depends_on="apply_gpu_optimisations"),
    OptionSpec(
        key="nv_mem_clock_mhz_offset", type="int", default=-1,
        description_id="opt.gpu.nv_mem_clock_mhz_offset",
        depends_on="apply_gpu_optimisations"),
    OptionSpec(
        key="amd_performance_level", type="choice", default="",
        choices=["auto", "low", "high", "manual"],
        description_id="opt.gpu.amd_performance_level",
        depends_on="apply_gpu_optimisations",
        comment="; AMD specific settings\n; Requires a relatively up to date "
                "AMDGPU kernel module"),
]


class GpuState:
    """Values chosen by the user for the ``[gpu]`` section."""

    def __init__(self) -> None:
        for spec in GPU_OPTIONS:
            setattr(self, spec.key, spec.default)


class GpuCore:
    """State and logic of the ``[gpu]`` section."""

    section_id = SECTION_ID
    options = GPU_OPTIONS

    def __init__(self) -> None:
        """Create the section state and install the speaking option accessors."""
        self.state = GpuState()
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
        """Allowed values of an option (the ``[gpu]`` options are all static)."""
        return list(spec.choices or [])

    @staticmethod
    def _is_written(spec: OptionSpec, value) -> bool:
        """True if the option is active (not empty and different from its default)."""
        if value is None or str(value) == "":
            return False
        return str(value) != str(spec.default)

    def is_active(self, spec: OptionSpec) -> bool:
        """True if an option is active; used to gate the dependent options."""
        return self._is_written(spec, getattr(self.state, spec.key))

    def _dependency_active(self, spec: OptionSpec) -> bool:
        """True if the option this one depends on is active (or there is none)."""
        if not spec.depends_on:
            return True
        dependency = next((option for option in self.options
                           if option.key == spec.depends_on), None)
        return self.is_active(dependency) if dependency else True

    def reset(self) -> None:
        """Reset every option of this section to its default value."""
        for spec in self.options:
            setattr(self.state, spec.key, spec.default)

    def render(self) -> str:
        """Render the ``[gpu]`` section, only with active, enabled options."""
        lines: List[str] = []
        for spec in self.options:
            # Skip the dependent options while their master switch is off.
            if not self._dependency_active(spec):
                continue
            value = getattr(self.state, spec.key)
            # Skip options still at their default: only active ones are written.
            if not self._is_written(spec, value):
                continue
            # Emit the definition comment above the option, when there is one.
            if spec.comment:
                lines.append(spec.comment)
            lines.append(spec.template.format(value=value))
        if not lines:
            return ""
        # Wrap the active lines in the section header; the file ends with "\n".
        return f"[{self.section_id}]\n" + "\n".join(lines) + "\n"

    def apply(self, section: Dict[str, List[str]]) -> None:
        """Apply the parsed ``[gpu]`` values (``key -> [raw values]``)."""
        for spec in self.options:
            raw_values = section.get(spec.key)
            if not raw_values:
                continue
            raw = raw_values[-1] if len(raw_values) == 1 else ",".join(raw_values)
            try:
                value: Optional[object]
                if spec.type == "int":
                    value = int(raw)
                else:
                    value = raw
            except ValueError:
                value = None
            if value is not None:
                setattr(self.state, spec.key, value)

    def apply_values(self, values: Dict[str, object]) -> None:
        """Set typed values (e.g. from the saved session) for this section."""
        for spec in self.options:
            full_key = f"{self.section_id}.{spec.key}"
            if full_key in values:
                setattr(self.state, spec.key, values[full_key])
