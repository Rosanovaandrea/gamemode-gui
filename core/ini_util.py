"""Minimal INI reader.

The standard :mod:`configparser` collapses repeated keys (it only keeps the
last occurrence), which is exactly what we need to preserve for list options
such as ``whitelist``/``blacklist``. So we ship a small, focused reader that:

* tracks every section,
* records repeated keys as Python lists,
* supports ``;``/``#`` comments and ``key = value`` assignment,
* ignores unknown/foreign keys (they are not part of the declarative table
  but the reader is permissive and simply returns them).
"""

from __future__ import annotations

from typing import Dict, List


def parse(text: str) -> Dict[str, Dict[str, List[str]]]:
    """Parse ``gamemode.ini`` ``text`` into *section -> key -> [values]*.

    Values are always lists so that a key repeated across several lines is
    captured completely. Callers decide whether to treat one element (scalar)
    or many (list).
    """
    result: Dict[str, Dict[str, List[str]]] = {}
    section = None
    current_key = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            current_key = None
            result.setdefault(section, {})
            continue

        if section is None:
            # Orphan content before any section: ignore.
            continue

        # key = value
        if "=" in line or ":" in line:
            sep = "=" if "=" in line else ":"
            name, _, value = line.partition(sep)
            name = name.strip()
            value = strip_inline_comment(value.strip())
            current_key = name
            result[section].setdefault(name, []).append(value)
        elif current_key is not None:
            # Continuation line of the previous key (leading whitespace
            # before any '=' is treated as a continuation value).
            result[section].setdefault(current_key, []).append(
                strip_inline_comment(line)
            )

    return result


def strip_inline_comment(value: str) -> str:
    """Remove an inline ``;``/``#`` comment from a value.

    Inih only strips inline comments when they are preceded by whitespace.
    We replicate that conservative behaviour.
    """
    for i, ch in enumerate(value):
        if ch in (";", "#") and (i == 0 or value[i - 1].isspace()):
            return value[:i].rstrip()
    return value


def parse_file(path: str) -> Dict[str, Dict[str, List[str]]]:
    with open(path, "r", encoding="utf-8") as fh:
        return parse(fh.read())