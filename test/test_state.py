"""State tests (no GUI): actions, reducers, selectors and dirty tracking."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state import (  # noqa: E402
    AppStore, load_action, option_action, reset_section, section_defaults,
)

defaults = {"demo": section_defaults([
    type("Spec", (), {"key": "value", "default": 1})(),
    type("Spec", (), {"key": "items", "default": ["a"]})(),
])}

store = AppStore(defaults)
assert store.section_state("demo") == {"value": 1, "items": ["a"]}
assert not store.is_dirty()

events = []
store.subscribe_section("demo", events.append)
store.dispatch(option_action("demo", "value", 7))
assert store.section_state("demo")["value"] == 7
assert events[-1]["value"] == 7
assert store.is_dirty()

store.dispatch(load_action("demo", {"items": ["b"]}, append=True))
assert store.section_state("demo")["items"] == ["a", "b"]

store.dispatch(reset_section("demo"))
assert store.section_state("demo") == {"value": 1, "items": ["a"]}

store.set_dirty(False)
assert not store.is_dirty()
print("ALL STATE TESTS PASSED")
