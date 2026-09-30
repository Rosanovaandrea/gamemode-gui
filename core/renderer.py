"""Pure rendering of the options table into a ``gamemode.ini`` string.

The renderer is a pure function: ``render_ini(flags, values)`` returns the 
full text of the file. It traverses ``OPTIONS`` and, for every option whose 
activation flag is ``True``, writes its comment (if any) and its formatted 
value. Comments and ordering are therefore preserved exactly as declared in 
the table -- no ``configparser`` round-trip that could mangle comments.
"""

from __future__ import annotations

from typing import Dict

from .options_table import OPTIONS, SECTIONS_ORDER, OptionSpec


def escape_value(text: str) -> str:
    """Make a free string safe for a single INI value line.

    - Compresses embedded newlines into spaces (repeated-key lists ).
    - Neutralises a leading ``;`` or ``#`` so the value is not read as a
      comment, and strips trailing whitespace.
    """
    text = text.strip()
    text = " ".join(text.splitlines())
    if text.startswith(";") or text.startswith("#"):
        text = "\\" + text
    return text


def render_option(spec: OptionSpec, value) -> str:
    """Format a single option value according to its declared ``type``."""
    if spec.type == "bool":
        return spec.template.format(value=1 if value else 0)

    if spec.type == "list":
        return "\n".join(
            spec.template.format(value=escape_value(item)) for item in value
        )

    if spec.type in ("string",):
        return spec.template.format(value=escape_value(str(value)))

    return spec.template.format(value=value)


def render_ini(flags: Dict[str, bool], values: Dict[str, object]) -> str:
    """Produce the full ``gamemode.ini`` text.

    :param flags:  logical activation flags keyed by ``option.id``.
    :param values: current values keyed by ``option.id``.
    """
    lines: list = []

    for section in SECTIONS_ORDER:
        section_lines: list = []
        for spec in OPTIONS:
            if spec.section != section:
                continue
            if not flags.get(spec.id, False):
                continue
            value = values.get(spec.id, spec.default)

            # Skip empty lists: an active list option with no entries would
            # produce nothing useful.
            if spec.type == "list" and not value:
                continue

            if spec.comment:
                section_lines.append(spec.comment)
            rendered = render_option(spec, value)
            section_lines.append(rendered)

        if section_lines:
            if lines:
                lines.append("")  # blank line between sections
            lines.append(f"[{section}]")
            lines.extend(section_lines)

    return "\n".join(lines) + "\n"


def default_ini() -> str:
    """Generate a valid file from the table defaults (used for reset)."""
    flags = {spec.id: True for spec in OPTIONS}
    values = {spec.id: spec.default for spec in OPTIONS}
    return render_ini(flags, values)