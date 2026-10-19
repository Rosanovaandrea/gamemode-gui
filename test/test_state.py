"""State tests (no GUI): section values, notifications and dirty tracking."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state.store import AppStore, section_defaults  # noqa: E402

defaults = {"demo": section_defaults([
    type("Spec", (), {"key": "value", "default": 1})(),
    type("Spec", (), {"key": "items", "default": ["a"]})(),
])}

store = AppStore(defaults)
assert store.section_state("demo") == {"value": 1, "items": ["a"]}
assert not store.is_dirty()

events = []
store.subscribe(lambda root: events.append(root["sections"]["demo"]))
store.set_option("demo", "value", 7)
assert store.section_state("demo")["value"] == 7
assert events[-1]["value"] == 7
assert store.is_dirty()

store.load_section("demo", {"items": ["b"]}, append=True)
assert store.section_state("demo")["items"] == ["a", "b"]

store.reset_section("demo")
assert store.section_state("demo") == {"value": 1, "items": ["a"]}

store.set_dirty(False)
assert not store.is_dirty()
print("ALL STATE TESTS PASSED")
