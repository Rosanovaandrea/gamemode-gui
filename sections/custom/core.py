"""Core of the Custom section: state, options and INI (de)serialisation.

Self-contained section for the ``[custom]`` keys: the start/end script lists and
the notification switches. A ``toggle_entry`` switch adds/removes a fixed string
to/from a target list; the string is stripped from the list when read and
re-added at render time, so there is a single source of truth for each entry.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from spec import OptionSpec

SECTION_ID = "custom"

CUSTOM_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="notify_start", type="toggle_entry", default=False,
        label_id="opt.custom.notify_start.label",
        description_id="opt.custom.notify_start",
        target="start", entry='notify-send "GameMode started"'),
    OptionSpec(
        key="notify_end", type="toggle_entry", default=False,
        label_id="opt.custom.notify_end.label",
        description_id="opt.custom.notify_end",
        target="end", entry='notify-send "GameMode ended"'),
    OptionSpec(
        key="start", type="list", default=[],
        description_id="opt.custom.start",
        comment="; Custom scripts executed (via /bin/sh) when GameMode starts"),
    OptionSpec(
        key="end", type="list", default=[],
        description_id="opt.custom.end",
        comment="; Custom scripts executed (via /bin/sh) when GameMode ends"),
    OptionSpec(
        key="script_timeout", type="int", default=10, min_value=0,
        description_id="opt.custom.script_timeout",
        comment="; Timeout for scripts (seconds). Scripts are killed if they do "
                "not complete in time."),
]


def escape_value(text: str) -> str:
    """Make a free-text value safe on a single INI line."""
    text = " ".join(text.strip().splitlines())
    if text.startswith(";") or text.startswith("#"):
        text = "\\" + text
    return text


class CustomState:
    """Values chosen by the user for the ``[custom]`` section."""

    def __init__(self) -> None:
        for spec in CUSTOM_OPTIONS:
            setattr(self, spec.key, spec.default)


class CustomCore:
    """State and logic of the ``[custom]`` section."""

    section_id = SECTION_ID
    options = CUSTOM_OPTIONS

    def __init__(self) -> None:
        self.state = CustomState()
        self._listeners: List[Callable[[str], None]] = []
        self._install_accessors()

    def subscribe(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def _notify(self, changed_key: str) -> None:
        for listener in self._listeners:
            listener(changed_key)

    def _install_accessors(self) -> None:
        for spec in self.options:
            setattr(self, f"get_{spec.key}", self._make_getter(spec.key))
            setattr(self, f"set_{spec.key}", self._make_setter(spec.key))

    def _make_getter(self, key: str):
        def get_option_value():
            return getattr(self.state, key)
        get_option_value.__name__ = f"get_{key}"
        return get_option_value

    def _make_setter(self, key: str):
        def set_option_value(value) -> None:
            setattr(self.state, key, value)
            self._notify(key)
        set_option_value.__name__ = f"set_{key}"
        return set_option_value

    def choices_for(self, spec: OptionSpec) -> List[str]:
        return list(spec.choices or [])

    def _effective_list(self, spec: OptionSpec) -> List[str]:
        """The list value plus the fixed strings of its active toggle entries."""
        items: List[str] = []
        for toggle in self.options:
            if (toggle.type == "toggle_entry" and toggle.target == spec.key
                    and getattr(self.state, toggle.key)):
                items.append(toggle.entry)
        items.extend(getattr(self.state, spec.key) or [])
        return items

    def is_active(self, spec: OptionSpec) -> bool:
        if spec.type == "list":
            return bool(self._effective_list(spec))
        if spec.type == "bool":
            return bool(getattr(self.state, spec.key)) != bool(spec.default)
        return bool(getattr(self.state, spec.key))

    def reset(self) -> None:
        """Reset every option of this section to its default value."""
        for spec in self.options:
            setattr(self.state, spec.key, spec.default)

    def render(self) -> str:
        """Render the ``[custom]`` section, only with active options."""
        lines: List[str] = []
        for spec in self.options:
            if spec.type == "toggle_entry":
                continue  # acts on the target list, no line of its own
            if spec.type == "list":
                items = self._effective_list(spec)
                if not items:
                    continue
                if spec.comment:
                    lines.append(spec.comment)
                for item in items:
                    lines.append(spec.template.format(value=escape_value(item)))
                continue
            value = getattr(self.state, spec.key)
            if value is None or value == spec.default:
                continue
            if spec.comment:
                lines.append(spec.comment)
            lines.append(spec.template.format(value=value))
        if not lines:
            return ""
        return f"[{self.section_id}]\n" + "\n".join(lines) + "\n"

    def apply(self, section: Dict[str, List[str]], append: bool = False) -> None:
        """Apply the parsed ``[custom]`` values (``key -> [raw values]``).

        With ``append`` the list options extend the current value (as GameMode
        does when merging the installed base with the ``/etc`` override).
        """
        for spec in self.options:
            raw_values = section.get(spec.key)
            if not raw_values:
                continue
            if spec.type == "list":
                parsed = [raw.strip() for raw in raw_values if raw.strip()]
                if append:
                    parsed = list(getattr(self.state, spec.key)) + parsed
                setattr(self.state, spec.key, parsed)
            elif spec.type == "toggle_entry":
                setattr(self.state, spec.key, True)
            else:
                raw = raw_values[-1]
                try:
                    setattr(self.state, spec.key, int(raw))
                except ValueError:
                    pass
        self._extract_toggle_entries()

    def _extract_toggle_entries(self) -> None:
        """Turn a managed string found in a list into its switch and drop it."""
        for toggle in self.options:
            if toggle.type != "toggle_entry" or not toggle.target or not toggle.entry:
                continue
            target = getattr(self.state, toggle.target)
            if isinstance(target, list) and toggle.entry in target:
                setattr(self.state, toggle.key, True)
                setattr(self.state, toggle.target,
                        [item for item in target if item != toggle.entry])

    def apply_values(self, values: Dict[str, object]) -> None:
        """Set typed values (e.g. from the saved session) for this section."""
        for spec in self.options:
            full_key = f"{self.section_id}.{spec.key}"
            if full_key in values:
                setattr(self.state, spec.key, values[full_key])
