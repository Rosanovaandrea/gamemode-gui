"""INI slice parsing shared by the section initializers."""

from __future__ import annotations

from typing import Dict, List


def extract_section(text: str, section_id: str) -> Dict[str, List[str]]:
    """Return ``key -> [raw values]`` for ``[section_id]`` from INI text."""
    result: Dict[str, List[str]] = {}
    section = None
    current_key = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match line:
            case _ if not line or line.startswith((";", "#")):
                continue
            case _ if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()
                current_key = None
            case _ if section == section_id and ("=" in line or ":" in line):
                separator = "=" if "=" in line else ":"
                name, _, value = line.partition(separator)
                current_key = name.strip()
                result.setdefault(current_key, []).append(strip_comment(value.strip()))
            case _ if section == section_id and current_key is not None:
                result.setdefault(current_key, []).append(strip_comment(line))
    return result


def strip_comment(value: str) -> str:
    """Remove a trailing ``;``/``#`` comment from a value."""
    for index, char in enumerate(value):
        if char in (";", "#") and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value
