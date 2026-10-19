"""Generic INI rendering/parsing used by the stateful sections."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from spec import OptionSpec
from utils.cpu import expand_cpu_list

Written = Callable[[OptionSpec, object], bool]
RenderValue = Callable[[OptionSpec, object], object]


def written_default(option_spec: OptionSpec, value) -> bool:
    """Write changed booleans, and non-empty values that differ from the default."""
    if option_spec.type == "bool":
        return bool(value) != bool(option_spec.default)
    if value is None or str(value) == "":
        return False
    return str(value) != str(option_spec.default)


def written_nonempty(option_spec: OptionSpec, value) -> bool:
    """Write set booleans and non-empty values (GPU/CPU rule)."""
    match option_spec.type:
        case "bool":
            return bool(value) != bool(option_spec.default)
        case _:
            return bool(value)


def bool_value(option_spec: OptionSpec, value) -> object:
    """Render booleans as 1/0."""
    match option_spec.type:
        case "bool":
            return 1 if value else 0
        case _:
            return value


def cpu_value(option_spec: OptionSpec, value) -> object:
    """Render core lists as comma-separated ids and booleans as 1/0."""
    match option_spec.type:
        case "cores":
            return ",".join(str(core) for core in value)
        case "bool":
            return 1 if value else 0
        case _:
            return value


def render_section(core, written: Written = written_default,
                   render_value: Optional[RenderValue] = None,
                   gate_dependencies: bool = False) -> str:
    """Render the active options of ``core`` as an INI section."""
    lines: List[str] = []
    for option_spec in core.options:
        value = getattr(core.state, option_spec.key)
        if ((gate_dependencies and not core.dependency_active(option_spec))
                or not written(option_spec, value)):
            continue
        if option_spec.comment:
            lines.append(option_spec.comment)
        rendered = render_value(option_spec, value) if render_value else value
        lines.append(option_spec.template.format(value=rendered))
    return f"[{core.section_id}]\n" + "\n".join(lines) + "\n" if lines else ""


def parse_value(option_spec: OptionSpec, values: List[str]):
    """Convert raw INI values to the option's Python type (or ``None``)."""
    match option_spec.type:
        case "int" | "float" | "bool":
            raw = values[-1]
        case "cores" | "list":
            raw = ",".join(values)
        case _:
            raw = values[-1] if len(values) == 1 else ",".join(values)
    try:
        match option_spec.type:
            case "int":
                return int(raw)
            case "float":
                return float(raw)
            case "bool":
                return raw.strip().lower() not in ("0", "false", "no")
            case "cores":
                return expand_cpu_list(",".join(values))
            case "list":
                return [item.strip() for item in values if item.strip()]
            case _:
                return raw
    except ValueError:
        return None


def parse_into(core, parsed: Dict[str, List[str]], append: bool = False) -> None:
    """Apply parsed values to ``core`` (lists optionally extend the current one)."""
    for option_spec in core.options:
        values = parsed.get(option_spec.key)
        value = parse_value(option_spec, values) if values else None
        if value is None:
            continue
        if append:
            match option_spec.type:
                case "list":
                    value = [*(getattr(core.state, option_spec.key) or []), *value]
        setattr(core.state, option_spec.key, value)
