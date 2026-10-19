"""Shared loading logic for the stateful sections."""

from __future__ import annotations

from typing import Dict, Optional

from gamemode_gui.config import extract_section, strip_comment


def load_section(core, base_text: str, override_text: str,
                 session_values: Optional[Dict[str, object]] = None,
                 append: bool = False) -> None:
    """Load one section core from the configuration texts / saved session."""
    core.reset_to_defaults()
    base = extract_section(base_text, core.section_id)
    override = extract_section(override_text, core.section_id)
    core.apply_parsed_section(base)
    if append:
        core.apply_parsed_section(override, append=True)
    else:
        core.apply_parsed_section(override)
    if not base and not override and session_values:
        core.apply_saved_values(session_values)


__all__ = ["extract_section", "load_section", "strip_comment"]
