"""Redux actions used by the application state."""

from __future__ import annotations

from typing import Any, Optional

from .vendor import create_action

SET_OPTION = "SET_OPTION"
LOAD_SECTION = "LOAD_SECTION"
RESET_SECTION = "RESET_SECTION"
INIT_SECTION = "INIT_SECTION"
SET_DIRTY = "SET_DIRTY"

set_option = create_action(SET_OPTION)
load_section = create_action(LOAD_SECTION)
reset_section = create_action(RESET_SECTION)
init_section = create_action(INIT_SECTION)
set_dirty = create_action(SET_DIRTY)


def option_action(section: str, key: str, value: Any):
    """Build a ``SET_OPTION`` action."""
    return set_option((section, key, value))


def load_action(section: str, values: dict, append: bool = False):
    """Build a ``LOAD_SECTION`` action."""
    return load_section((section, values, append))


def init_action(section: str, values: dict):
    """Build an ``INIT_SECTION`` action."""
    return init_section((section, values))


def dirty_action(value: bool):
    """Build a ``SET_DIRTY`` action."""
    return set_dirty(bool(value))
