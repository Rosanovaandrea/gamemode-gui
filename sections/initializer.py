"""Shared initializer logic for the stateful sections.

Every section initializer does the same thing: reset the section core, parse the
``[<section>]`` slice out of the installed base and the ``/etc`` override, apply
them (the custom section *appends* its lists, as GameMode does when merging the
files) and fall back to the saved session only when there was nothing to read.

That logic lives here, so each ``sections/<name>/initializer.py`` is left with
just its entry point (:func:`load_section`, with the right section-specific
options) instead of a copy of the parser.
"""

from __future__ import annotations

from typing import Dict, List, Optional


def load_section(core, base_text: str, override_text: str,
                 session_values: Optional[Dict[str, object]] = None,
                 append: bool = False) -> None:
    """Load one section core from the configuration texts / saved session.

    ``append`` is used by the custom section: its list options extend the base
    instead of replacing it, which is how GameMode merges the two files. The
    saved session is only a fallback, used when neither text had the section, so
    a restore that leaves the file empty resets the section to its defaults.
    """
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


def extract_section(text: str, section_id: str) -> Dict[str, List[str]]:
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
            result.setdefault(current_key, []).append(strip_comment(value.strip()))
        elif current_key is not None:
            result.setdefault(current_key, []).append(strip_comment(line))
    return result


def strip_comment(value: str) -> str:
    """Remove a trailing ``;``/``#`` comment from a value."""
    for index, char in enumerate(value):
        if char in (";", "#") and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value
