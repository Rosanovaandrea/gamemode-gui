"""Shared base for the stateful section cores.

The state now lives in a single application store. ``SectionCore`` is a thin facade:
it installs speaking getters/setters, reads selectors and forwards changes to
the existing view listeners, so the section APIs stay unchanged.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from state.store import AppStore, section_defaults
from configuration import extract_section
from sections.serialization import parse_into, render_section, written_default
from spec import OptionSpec


class SectionState:
    """Attribute-style view over one section's store values."""

    __slots__ = ("_core",)

    def __init__(self, core: "SectionCore") -> None:
        object.__setattr__(self, "_core", core)

    def __getattr__(self, key: str):
        if key.startswith("_"):
            raise AttributeError(key)
        return self._core._get_option(key)

    def __setattr__(self, key: str, value) -> None:
        if key.startswith("_"):
            object.__setattr__(self, key, value)
        else:
            self._core._set_option(key, value)


class SectionCore:
    """Common machinery of a stateful section core."""

    section_id = ""
    options: List[OptionSpec] = []
    append_on_load = False
    gate_dependencies = False
    written_rule = staticmethod(written_default)
    render_value = None

    def __init__(self, store: Optional[AppStore] = None) -> None:
        """Register the section defaults and install the option accessors."""
        self._defaults = section_defaults(self.options)
        self.store = store or AppStore({self.section_id: self._defaults})
        self.store.ensure_section(self.section_id, self._defaults)
        self.state = SectionState(self)
        for option in self.options:
            setattr(self, f"get_{option.key}", self._make_option_getter(option.key))
            setattr(self, f"set_{option.key}", self._make_option_setter(option.key))

    # -- speaking accessors, one per option ----------------------------------
    def _make_option_getter(self, option_key: str):
        def get_option_value():
            return self._get_option(option_key)
        get_option_value.__name__ = f"get_{option_key}"
        return get_option_value

    def _make_option_setter(self, option_key: str):
        def set_option_value(value) -> None:
            self._set_option(option_key, value)
        set_option_value.__name__ = f"set_{option_key}"
        return set_option_value

    def _get_option(self, option_key: str):
        return self.store.section_state(self.section_id).get(option_key)

    def _set_option(self, option_key: str, value) -> None:
        self.store.set_option(self.section_id, option_key, value)

    # -- allowed values ------------------------------------------------------
    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        """Allowed values of an option (static; overridden if kernel-derived)."""
        return list(option.choices or [])

    def dependency_active(self, option: OptionSpec) -> bool:
        """True when the option this one depends on is active (or there is none)."""
        if not option.depends_on:
            return True
        dependency = next((candidate for candidate in self.options
                           if candidate.key == option.depends_on), None)
        return self.is_option_active(dependency) if dependency else True

    # -- rendering / parsing (common defaults) -------------------------------
    def is_option_active(self, option: OptionSpec) -> bool:
        """True when the option contributes a line to the section."""
        return self.written_rule(option, getattr(self.state, option.key))

    def render_ini_section(self) -> str:
        """Render the active options using this section's write rule."""
        return render_section(self, written=self.written_rule,
                              render_value=self.render_value,
                              gate_dependencies=self.gate_dependencies)

    def apply_parsed_section(self, parsed_section: Dict[str, List[str]]) -> None:
        """Apply parsed values with the shared typed parser."""
        parse_into(self, parsed_section)

    # -- state ---------------------------------------------------------------
    def load_texts(self, base_text: str, override_text: str,
                   session_values: Optional[Dict[str, object]] = None) -> None:
        """Load this section from the base/override texts and the session."""
        self.reset_to_defaults()
        base = extract_section(base_text, self.section_id)
        override = extract_section(override_text, self.section_id)
        self.apply_parsed_section(base)
        if self.append_on_load:
            self.apply_parsed_section(override, append=True)
        else:
            self.apply_parsed_section(override)
        if not base and not override and session_values:
            self.apply_saved_values(session_values)

    def reset_to_defaults(self) -> None:
        """Reset every option of this section to its default value."""
        self.store.reset_section(self.section_id)

    def apply_saved_values(self, saved_values: Dict[str, object]) -> None:
        """Set typed saved-session values for this section."""
        selected = {}
        for option in self.options:
            flat_key = f"{self.section_id}.{option.key}"
            if flat_key in saved_values:
                selected[option.key] = saved_values[flat_key]
        if selected:
            self.store.load_section(self.section_id, selected)
