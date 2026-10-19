"""Core of the Custom section: state and INI (de)serialisation.

Self-contained section for the ``[custom]`` keys: the start/end script lists and
the notification switches; the options live in :mod:`sections.custom.options` and
the shared core machinery is in :mod:`sections.core`. A ``toggle_entry`` switch
adds/removes a fixed string to/from a target list; the string is stripped from
the list when read and re-added at render time, so there is a single source of
truth for each entry.
"""

from __future__ import annotations

from typing import Dict, List

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

    def _effective_list_value(self, option: OptionSpec) -> List[str]:
        """The list value plus the fixed strings of its active toggle entries."""
        list_items: List[str] = []
        for toggle_option in self.options:
            # An active toggle targeting this list contributes its fixed string first.
            if (toggle_option.type == "toggle_entry"
                    and toggle_option.target == option.key
                    and getattr(self.state, toggle_option.key)):
                list_items.append(toggle_option.entry)
        # Then come the free-form items the user typed in the list editor.
        list_items.extend(getattr(self.state, option.key) or [])
        return list_items

    def is_option_active(self, option: OptionSpec) -> bool:
        """True if an option is active (a non-empty list, or a set switch)."""
        if option.type == "list":
            return bool(self._effective_list_value(option))
        if option.type == "bool":
            return bool(getattr(self.state, option.key)) != bool(option.default)
        return bool(getattr(self.state, option.key))

    def render_ini_section(self) -> str:
        """Render the ``[custom]`` section, only with active options."""
        rendered_lines: List[str] = []
        for option in self.options:
            # A toggle_entry has no line of its own: it acts on the target list.
            if option.type == "toggle_entry":
                continue
            # A list is written as repeated keys: one line per item.
            if option.type == "list":
                list_items = self._effective_list_value(option)
                if not list_items:
                    continue
                if option.comment:
                    rendered_lines.append(option.comment)
                for list_item in list_items:
                    escaped_item = escape_value(list_item)
                    rendered_lines.append(option.template.format(value=escaped_item))
                continue
            # A scalar (e.g. the script timeout) is written only if activated.
            value = getattr(self.state, option.key)
            if value is None or value == option.default:
                continue
            if option.comment:
                rendered_lines.append(option.comment)
            rendered_lines.append(option.template.format(value=value))
        if not rendered_lines:
            return ""
        # Wrap the active lines in the section header; the file ends with "\n".
        return f"[{self.section_id}]\n" + "\n".join(rendered_lines) + "\n"

    def apply_parsed_section(self, parsed_section: Dict[str, List[str]],
                             append: bool = False) -> None:
        """Apply the parsed ``[custom]`` values (``key -> [raw values]``).

        With ``append`` the list options extend the current value (as GameMode
        does when merging the installed base with the ``/etc`` override).
        """
        for option in self.options:
            raw_option_values = parsed_section.get(option.key)
            if not raw_option_values:
                continue
            if option.type == "list":
                parsed_items = [raw_item.strip() for raw_item in raw_option_values
                                if raw_item.strip()]
                if append:
                    current_items = getattr(self.state, option.key)
                    parsed_items = list(current_items) + parsed_items
                setattr(self.state, option.key, parsed_items)
            elif option.type == "toggle_entry":
                setattr(self.state, option.key, True)
            else:
                raw_value = raw_option_values[-1]
                try:
                    setattr(self.state, option.key, int(raw_value))
                except ValueError:
                    pass
        self._extract_toggle_entries_from_lists()

    def _extract_toggle_entries_from_lists(self) -> None:
        """Turn a managed string found in a list into its switch and drop it."""
        for toggle_option in self.options:
            if (toggle_option.type != "toggle_entry"
                    or not toggle_option.target or not toggle_option.entry):
                continue
            target_items = getattr(self.state, toggle_option.target)
            if isinstance(target_items, list) and toggle_option.entry in target_items:
                setattr(self.state, toggle_option.key, True)
                remaining_items = [item for item in target_items
                                   if item != toggle_option.entry]
                setattr(self.state, toggle_option.target, remaining_items)
