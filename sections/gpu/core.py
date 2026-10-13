"""Core of the GPU section: state and INI (de)serialisation.

Self-contained section for the ``[gpu]`` keys; the options live in
:mod:`sections.gpu.options` and the shared core machinery is in
:mod:`sections.core`. The options other than ``apply_gpu_optimisations`` depend
on it, so they are only written (and enabled in the view) when the master switch
is on.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sections.core import SectionCore
from sections.gpu.options import GPU_OPTIONS
from spec import OptionSpec

SECTION_ID = "gpu"


class GpuCore(SectionCore):
    """State and logic of the ``[gpu]`` section."""

    section_id = SECTION_ID
    options = GPU_OPTIONS

    # -- rendering -----------------------------------------------------------
    @staticmethod
    def _is_option_written(option: OptionSpec, value) -> bool:
        """True if the option is active (not empty and different from its default)."""
        if value is None or str(value) == "":
            return False
        return str(value) != str(option.default)

    def is_option_active(self, option: OptionSpec) -> bool:
        """True if an option is active; used to gate the dependent options."""
        return self._is_option_written(option, getattr(self.state, option.key))

    def _is_dependency_active(self, option: OptionSpec) -> bool:
        """True if the option this one depends on is active (or there is none)."""
        if not option.depends_on:
            return True
        dependency_option = next((candidate for candidate in self.options
                                  if candidate.key == option.depends_on), None)
        return self.is_option_active(dependency_option) if dependency_option else True

    def render_ini_section(self) -> str:
        """Render the ``[gpu]`` section, only with active, enabled options."""
        rendered_lines: List[str] = []
        for option in self.options:
            # Skip the dependent options while their master switch is off.
            if not self._is_dependency_active(option):
                continue
            value = getattr(self.state, option.key)
            # Skip options still at their default: only active ones are written.
            if not self._is_option_written(option, value):
                continue
            # Emit the definition comment above the option, when there is one.
            if option.comment:
                rendered_lines.append(option.comment)
            rendered_lines.append(option.template.format(value=value))
        if not rendered_lines:
            return ""
        # Wrap the active lines in the section header; the file ends with "\n".
        return f"[{self.section_id}]\n" + "\n".join(rendered_lines) + "\n"

    # -- reading -------------------------------------------------------------
    def apply_parsed_section(self, parsed_section: Dict[str, List[str]]) -> None:
        """Apply the parsed ``[gpu]`` values (``key -> [raw values]``)."""
        for option in self.options:
            raw_option_values = parsed_section.get(option.key)
            if not raw_option_values:
                continue
            raw_value = (raw_option_values[-1] if len(raw_option_values) == 1
                         else ",".join(raw_option_values))
            try:
                value: Optional[object]
                if option.type == "int":
                    value = int(raw_value)
                else:
                    value = raw_value
            except ValueError:
                value = None
            if value is not None:
                setattr(self.state, option.key, value)
