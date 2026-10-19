"""Core of the Custom section."""

from __future__ import annotations

from typing import Dict, List, Optional

from sections.core import SectionCore
from sections.custom.options import CUSTOM_OPTIONS
from spec import OptionSpec

SECTION_ID = "custom"


def escape_value(text: str) -> str:
    """Make a free-text value safe on a single INI line."""
    text = " ".join(text.strip().splitlines())
    if text.startswith(";") or text.startswith("#"):
        text = "\\" + text
    return text


class CustomCore(SectionCore):
    """State and logic of the ``[custom]`` section."""

    section_id = SECTION_ID
    options = CUSTOM_OPTIONS

    # -- option lookup -------------------------------------------------------
    def _option(self, key: str) -> Optional[OptionSpec]:
        """Return the option descriptor with ``key``, if it exists."""
        return next((spec for spec in self.options if spec.key == key), None)

    # -- effective values ----------------------------------------------------
    def _effective_list_value(self, list_spec: OptionSpec) -> List[str]:
        """The list items, preceded by the fixed entries of active toggles."""
        fixed_entries = [
            toggle_spec.entry
            for toggle_spec in self.options
            if toggle_spec.type == "toggle_entry"
            and toggle_spec.target == list_spec.key
            and getattr(self.state, toggle_spec.key)
        ]
        return [*fixed_entries, *(getattr(self.state, list_spec.key) or [])]

    def is_option_active(self, option_spec: OptionSpec) -> bool:
        """True when the option contributes a line to the section."""
        value = getattr(self.state, option_spec.key)
        match option_spec.type:
            case "list":
                return bool(self._effective_list_value(option_spec))
            case "bool":
                return bool(value) != bool(option_spec.default)
            case _:
                return bool(value)

    # -- rendering -----------------------------------------------------------
    def render_ini_section(self) -> str:
        """Build the ``[custom]`` block.

        Three cases:
        - ``toggle_entry``: no line of its own (it feeds its target list);
        - ``list``: one repeated ``key=value`` line per item;
        - scalar: one line, only when the value differs from its default.
        """
        lines: List[str] = []
        for option_spec in self.options:
            lines.extend(self._render_option(option_spec))
        if not lines:
            return ""
        return f"[{self.section_id}]\n" + "\n".join(lines) + "\n"

    def _render_option(self, option_spec: OptionSpec) -> List[str]:
        """Choose how one option is written, based on its type."""
        match option_spec.type:
            case "toggle_entry":
                return []                       # represented by its target list
            case "list":
                return self._render_list(option_spec)
            case _:
                return self._render_scalar(option_spec)

    def _render_list(self, option_spec: OptionSpec) -> List[str]:
        """Render a list as one repeated ``key=value`` line per item."""
        items = self._effective_list_value(option_spec)
        if not items:
            return []
        lines = [option_spec.comment] if option_spec.comment else []
        lines.extend(option_spec.template.format(value=escape_value(item))
                     for item in items)
        return lines

    def _render_scalar(self, option_spec: OptionSpec) -> List[str]:
        """Render a single value, but only when it differs from its default."""
        value = getattr(self.state, option_spec.key)
        if value is None or value == option_spec.default:
            return []
        lines = [option_spec.comment] if option_spec.comment else []
        lines.append(option_spec.template.format(value=value))
        return lines

    # -- parsing -------------------------------------------------------------
    def apply_parsed_section(self, parsed_section: Dict[str, List[str]],
                             append: bool = False) -> None:
        """Apply parsed values; ``append`` extends the script lists."""
        for option_spec in self.options:
            raw_values = parsed_section.get(option_spec.key)
            if raw_values:
                match option_spec.type:
                    case "list":
                        self._apply_list(option_spec, raw_values, append)
                    case "toggle_entry":
                        self._set_option(option_spec.key, True)
                    case "int":
                        self._apply_int(option_spec, raw_values)
                    case _:
                        self._set_option(option_spec.key, raw_values[-1])
        self._extract_toggle_entries_from_lists()

    def _apply_list(self, option_spec: OptionSpec, raw_values: List[str],
                    append: bool) -> None:
        """Store the list items, optionally after the current ones."""
        parsed_items = [raw.strip() for raw in raw_values if raw.strip()]
        if append:
            parsed_items = [*(getattr(self.state, option_spec.key) or []),
                            *parsed_items]
        self._set_option(option_spec.key, parsed_items)

    def _apply_int(self, option_spec: OptionSpec, raw_values: List[str]) -> None:
        """Store an integer value, ignoring invalid input."""
        try:
            self._set_option(option_spec.key, int(raw_values[-1]))
        except ValueError:
            pass

    def _extract_toggle_entries_from_lists(self) -> None:
        """Turn a managed string found in a list into its switch and drop it."""
        for toggle_spec in self.options:
            target_spec = self._option(toggle_spec.target) if toggle_spec.target else None
            target_items = (
                getattr(self.state, target_spec.key)
                if target_spec is not None and target_spec.type == "list"
                else []
            )
            if (toggle_spec.type == "toggle_entry"
                    and toggle_spec.entry
                    and toggle_spec.entry in target_items):
                self._set_option(toggle_spec.key, True)
                self._set_option(target_spec.key,
                                 [item for item in target_items
                                  if item != toggle_spec.entry])
