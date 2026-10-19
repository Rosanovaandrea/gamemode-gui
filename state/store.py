"""Small application store: a dict of section values plus a dirty flag."""

from __future__ import annotations

import copy
from typing import Callable, Dict, Iterable, Optional


def _deep(value):
    return copy.deepcopy(value)


class AppStore:
    """Owns the section values and notifies subscribers after each change."""

    def __init__(self, defaults: Optional[Dict[str, dict]] = None) -> None:
        self._defaults: Dict[str, dict] = _deep(defaults or {})
        self._sections: Dict[str, dict] = _deep(defaults or {})
        self._dirty = False
        self._listeners: list[Callable[[dict], None]] = []

    # -- section lifecycle ---------------------------------------------------
    def ensure_section(self, section_id: str, defaults: Dict[str, object]) -> None:
        """Register a section and fill any missing default values."""
        self._defaults.setdefault(section_id, _deep(defaults))
        values = self._sections.setdefault(section_id, {})
        for key, value in defaults.items():
            values.setdefault(key, _deep(value))
        self._notify()

    def section_state(self, section_id: str) -> dict:
        """Current values of one section (a copy)."""
        return _deep(self._sections.get(
            section_id, self._defaults.get(section_id, {})))

    def get_state(self) -> dict:
        """Whole state, as consumed by the window."""
        return {"sections": _deep(self._sections), "dirty": self._dirty}

    # -- mutations -----------------------------------------------------------
    def set_option(self, section_id: str, key: str, value) -> None:
        """Set one option and notify subscribers."""
        values = self._sections.setdefault(
            section_id, _deep(self._defaults.get(section_id, {})))
        values[key] = _deep(value)
        self._dirty = True
        self._notify()

    def load_section(self, section_id: str, values: Dict[str, object],
                     append: bool = False) -> None:
        """Load several typed values; lists can be appended instead of replaced."""
        current = self._sections.setdefault(
            section_id, _deep(self._defaults.get(section_id, {})))
        for key, value in values.items():
            if append and isinstance(current.get(key), list) and isinstance(value, list):
                current[key] = [*current[key], *_deep(value)]
            else:
                current[key] = _deep(value)
        self._dirty = True
        self._notify()

    def reset_section(self, section_id: str) -> None:
        """Restore one section to its defaults."""
        self._sections[section_id] = _deep(self._defaults.get(section_id, {}))
        self._dirty = True
        self._notify()

    def set_dirty(self, value: bool) -> None:
        """Set the dirty flag and notify only when it changes."""
        value = bool(value)
        if value == self._dirty:
            return
        self._dirty = value
        self._notify()

    def is_dirty(self) -> bool:
        return self._dirty

    # -- subscription --------------------------------------------------------
    def subscribe(self, listener: Callable[[dict], None]) -> None:
        """Register a callback and immediately send the current state."""
        self._listeners.append(listener)
        listener(self.get_state())

    def _notify(self) -> None:
        state = self.get_state()
        for listener in list(self._listeners):
            listener(state)


def section_defaults(options: Iterable) -> dict:
    """Build the default values mapping from an option list."""
    return {option_spec.key: _deep(option_spec.default) for option_spec in options}
