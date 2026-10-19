"""Application store: a small, immutable Redux layer over the vendored redux-py."""

from __future__ import annotations

import copy
from typing import Callable, Dict, Iterable, Optional

from .actions import ActionType, dirty_action, init_action
from .vendor import create_feature_module, create_store


def _initial_state() -> dict:
    return {"sections": {}, "dirty": False}


def _deep(value):
    return copy.deepcopy(value)


class AppStore:
    """Store for all section values plus the window dirty flag.

    Reducers are pure and return new mappings. Views subscribe with a callback;
    the callbacks receive the whole root state (``sections`` + ``dirty``).
    """

    def __init__(self, defaults: Optional[Dict[str, dict]] = None) -> None:
        self._defaults: Dict[str, dict] = _deep(defaults or {})
        self._state = _initial_state()
        self._listeners: list[Callable[[dict], None]] = []
        self._store = create_store()
        self._store.add_feature_module(create_feature_module("app", self._reduce))
        self._store.as_observable().subscribe(self._received)
        for section_id, values in self._defaults.items():
            self.ensure_section(section_id, values)

    # -- reducers ------------------------------------------------------------
    def _reduce(self, state: Optional[dict], action) -> dict:
        state = _deep(state) if state else _initial_state()
        sections = state["sections"]
        action_type = getattr(action, "type", "")
        match action_type:
            case ActionType.INIT_SECTION:
                section_id, values = action.payload
                sections[section_id] = {
                    **_deep(self._defaults.get(section_id, {})),
                    **_deep(values),
                    **sections.get(section_id, {}),
                }
            case ActionType.SET_OPTION:
                section_id, key, value = action.payload
                values = dict(sections.get(section_id, self._defaults.get(section_id, {})))
                values[key] = _deep(value)
                sections[section_id] = values
                state["dirty"] = True
            case ActionType.LOAD_SECTION:
                section_id, values, append = action.payload
                current = dict(sections.get(section_id, self._defaults.get(section_id, {})))
                for key, value in values.items():
                    current[key] = self._merged_value(current.get(key), value, append)
                sections[section_id] = current
                state["dirty"] = True
            case ActionType.RESET_SECTION:
                section_id = action.payload
                sections[section_id] = _deep(self._defaults.get(section_id, {}))
                state["dirty"] = True
            case ActionType.SET_DIRTY:
                state["dirty"] = bool(action.payload)
        return state

    @staticmethod
    def _merged_value(previous, value, append: bool):
        """Replace a value, or append to it when both sides are lists."""
        if append and isinstance(previous, list) and isinstance(value, list):
            return [*previous, *_deep(value)]
        return _deep(value)

    # -- store API -----------------------------------------------------------
    def _received(self, root: dict) -> None:
        self._state = root.get("app", _initial_state())
        for listener in list(self._listeners):
            listener(self._state)

    def dispatch(self, action) -> None:
        self._store.dispatch(action)

    def ensure_section(self, section_id: str, defaults: Dict[str, object]) -> None:
        """Register a section and its defaults (idempotent)."""
        self._defaults.setdefault(section_id, _deep(defaults))
        self.dispatch(init_action(section_id, defaults))

    def section_state(self, section_id: str) -> dict:
        """Current values of one section (a copy)."""
        return _deep(self._state["sections"].get(section_id, self._defaults.get(section_id, {})))

    def get_state(self) -> dict:
        """Current root state (a copy)."""
        return _deep(self._state)

    def set_dirty(self, value: bool) -> None:
        self.dispatch(dirty_action(value))

    def is_dirty(self) -> bool:
        return bool(self._state.get("dirty", False))

    def subscribe(self, listener: Callable[[dict], None]) -> None:
        """Register a callback and immediately send the current state."""
        self._listeners.append(listener)
        listener(self._state)


def section_defaults(options: Iterable) -> dict:
    """Build the default values mapping from an option list."""
    return {option_spec.key: _deep(option_spec.default) for option_spec in options}
