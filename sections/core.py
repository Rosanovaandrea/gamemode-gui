"""Shared base for the stateful section cores.

Every section core is the same machine around different options: a state built
from the option defaults, a "speaking" getter/setter per option with change
notification (React-like), a reset to the defaults, and a way to load typed
values (from the saved session). That machinery is identical in every section, so
it lives here.

Each ``sections/<name>/core.py`` therefore only declares ``section_id`` and
``options`` and implements the section-specific rules: ``render_ini_section``,
``apply_parsed_section`` and ``is_option_active`` (and ``allowed_values_for`` only
when the allowed values come from the kernel). The shared state/accessor logic is
not repeated any more.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from spec import OptionSpec


class SectionState:
    """Values chosen by the user for one section (one attribute per option)."""

    def __init__(self, options: List[OptionSpec]) -> None:
        for option in options:
            setattr(self, option.key, option.default)


class SectionCore:
    """Common machinery of a stateful section core.

    A subclass sets ``section_id`` and ``options`` and implements
    ``render_ini_section``, ``apply_parsed_section`` and ``is_option_active``;
    ``allowed_values_for`` is only overridden when the allowed values are read
    from the kernel. Everything else (the state, the speaking accessors, change
    notification, reset and loading saved values) is provided here.
    """

    section_id = ""
    options: List[OptionSpec] = []

    def __init__(self) -> None:
        """Create the section state and install the speaking option accessors."""
        self.state = SectionState(self.options)
        self._change_listeners: List[Callable[[str], None]] = []
        self._install_option_accessors()

    # -- change notification (React-like) ------------------------------------
    def subscribe_change_listener(self, listener: Callable[[str], None]) -> None:
        """Register a view callback; it receives the option key that changed."""
        self._change_listeners.append(listener)

    def _notify_change_listeners(self, changed_option_key: str) -> None:
        """Notify every subscribed view that one option changed."""
        for listener in self._change_listeners:
            listener(changed_option_key)

    # -- speaking accessors, one per option ----------------------------------
    def _install_option_accessors(self) -> None:
        """Create a speaking ``get_<key>`` and ``set_<key>`` for every option."""
        for option in self.options:
            setattr(self, f"get_{option.key}", self._make_option_getter(option.key))
            setattr(self, f"set_{option.key}", self._make_option_setter(option.key))

    def _make_option_getter(self, option_key: str):
        """Return the ``get_<key>`` closure that reads one option from the state."""
        def get_option_value():
            return getattr(self.state, option_key)
        get_option_value.__name__ = f"get_{option_key}"
        get_option_value.__doc__ = f"Current value of the '{option_key}' option."
        return get_option_value

    def _make_option_setter(self, option_key: str):
        """Return the ``set_<key>`` closure that writes one option and notifies."""
        def set_option_value(value) -> None:
            setattr(self.state, option_key, value)
            self._notify_change_listeners(option_key)
        set_option_value.__name__ = f"set_{option_key}"
        set_option_value.__doc__ = f"Set the '{option_key}' option and notify the views."
        return set_option_value

    # -- allowed values ------------------------------------------------------
    def allowed_values_for(self, option: OptionSpec) -> List[str]:
        """Allowed values of an option (static; overridden if kernel-derived)."""
        return list(option.choices or [])

    # -- state ---------------------------------------------------------------
    def reset_to_defaults(self) -> None:
        """Reset every option of this section to its default value."""
        for option in self.options:
            setattr(self.state, option.key, option.default)

    def apply_saved_values(self, saved_values: Dict[str, object]) -> None:
        """Set typed values (e.g. from the saved session) for this section."""
        for option in self.options:
            section_option_key = f"{self.section_id}.{option.key}"
            if section_option_key in saved_values:
                setattr(self.state, option.key, saved_values[section_option_key])
