"""Generic INI rendering/parsing used by the stateful sections."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from spec import OptionSpec
from utils import expand_cpu_list

Written = Callable[[OptionSpec, object], bool]
RenderValue = Callable[[OptionSpec, object], object]


def written_default(option: OptionSpec, value) -> bool:
    """Default rule: write booleans when changed, others when non-empty/non-default."""
    if option.type == "bool":
        return bool(value) != bool(option.default)
    if value is None or str(value) == "":
        return False
    return str(value) != str(option.default)


def written_nonempty(option: OptionSpec, value) -> bool:
    """Rule used by GPU/CPU: a set switch or a non-empty value."""
    if option.type == "bool":
        return bool(value) != bool(option.default)
    return bool(value)


def bool_value(option: OptionSpec, value) -> object:
    """Render booleans as 1/0."""
    return (1 if value else 0) if option.type == "bool" else value


def cpu_value(option: OptionSpec, value) -> object:
    """Render core lists as comma-separated ids and booleans as 1/0."""
    if option.type == "cores":
        return ",".join(str(core) for core in value)
    return (1 if value else 0) if option.type == "bool" else value


def render_section(core, written: Written = written_default,
                   render_value: Optional[RenderValue] = None,
                   gate_dependencies: bool = False) -> str:
    """Render the active options of ``core`` as an INI section."""
    lines: List[str] = []
    for option in core.options:
        if gate_dependencies and not core.dependency_active(option):
            continue
        value = getattr(core.state, option.key)
        if not written(option, value):
            continue
        if option.comment:
            lines.append(option.comment)
        rendered = render_value(option, value) if render_value else value
        lines.append(option.template.format(value=rendered))
    return f"[{core.section_id}]\n" + "\n".join(lines) + "\n" if lines else ""


def _raw_value(option: OptionSpec, values: List[str]) -> str:
    if option.type in ("int", "float", "bool"):
        return values[-1]
    if option.type in ("cores", "list"):
        return ",".join(values)
    return values[-1] if len(values) == 1 else ",".join(values)


def parse_value(option: OptionSpec, values: List[str]):
    """Convert raw INI values to the option's Python type (or ``None``)."""
    raw = _raw_value(option, values)
    try:
        if option.type == "int":
            return int(raw)
        if option.type == "float":
            return float(raw)
        if option.type == "bool":
            return raw.strip().lower() not in ("0", "false", "no")
        if option.type == "cores":
            return expand_cpu_list(",".join(values))
        if option.type == "list":
            return [item.strip() for item in values if item.strip()]
        return raw
    except ValueError:
        return None


def parse_into(core, parsed: Dict[str, List[str]], append: bool = False) -> None:
    """Apply parsed values to ``core`` (lists optionally extend the current one)."""
    for option in core.options:
        values = parsed.get(option.key)
        if not values:
            continue
        value = parse_value(option, values)
        if value is None:
            continue
        if append and option.type == "list":
            value = list(getattr(core.state, option.key)) + list(value)
        setattr(core.state, option.key, value)
