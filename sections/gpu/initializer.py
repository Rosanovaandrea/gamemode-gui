"""Initializer of the GPU section.

Reads the ``[gpu]`` keys from the installed base and the ``/etc`` override (and,
only when neither exists, from the saved session) and puts them into the state.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sections.gpu.core import GpuCore


def initialize(core: GpuCore, base_text: str, override_text: str,
               session_values: Optional[Dict[str, object]] = None) -> None:
    """Load the GPU state from the configuration texts / session."""
    core.reset()
    base = _extract_section(base_text, core.section_id)
    override = _extract_section(override_text, core.section_id)
    core.apply(base)
    core.apply(override)
    if not base and not override and session_values:
        core.apply_values(session_values)


def _extract_section(text: str, section_id: str) -> Dict[str, List[str]]:
    """Return ``key -> [raw values]`` for ``[section_id]`` from INI text."""
    result: Dict[str, List[str]] = {}
    section = None
    current_key = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            current_key = None
            continue
        if section != section_id:
            continue
        if "=" in line or ":" in line:
            separator = "=" if "=" in line else ":"
            name, _, value = line.partition(separator)
            current_key = name.strip()
            result.setdefault(current_key, []).append(_strip_comment(value.strip()))
        elif current_key is not None:
            result.setdefault(current_key, []).append(_strip_comment(line))
    return result


def _strip_comment(value: str) -> str:
    """Remove a trailing ``;``/``#`` comment from a value."""
    for index, char in enumerate(value):
        if char in (";", "#") and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value
