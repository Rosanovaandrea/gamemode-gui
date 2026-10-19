"""Widget factory: maps an option type to its control via a registry."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from .controls import ChoicePicker, CoresEditor, ListEditor, StepperBox, SwitchBox

Builder = Callable[..., Gtk.Widget]
_FACTORIES: Dict[str, Builder] = {}


def register(option_type: str):
    """Register the builder for one option type."""
    def decorator(builder: Builder) -> Builder:
        _FACTORIES[option_type] = builder
        return builder
    return decorator


@register("int")
def _int(spec, on_change, choices, **_) -> Gtk.Widget:
    return StepperBox(float(spec.default or 0), spec.min_value, spec.max_value,
                      step=1, digits=0, on_change=on_change)


@register("float")
def _float(spec, on_change, choices, **_) -> Gtk.Widget:
    return StepperBox(float(spec.default or 0), spec.min_value, spec.max_value,
                      step=0.1, digits=2, on_change=on_change)


@register("bool")
@register("toggle_entry")
def _bool(spec, on_change, choices, **_) -> Gtk.Widget:
    return SwitchBox(active=bool(spec.default), on_change=on_change)


@register("enable")
def _enable(spec, on_change, choices, **_) -> Gtk.Widget:
    return SwitchBox(active=str(spec.default) == str(spec.on_value),
                     on_value=spec.on_value, off_value=spec.default,
                     on_change=on_change)


@register("choice")
def _choice(spec, on_change, choices, **_) -> Gtk.Widget:
    available = list(choices) if choices is not None else list(spec.choices or [])
    return ChoicePicker(choices=available, on_change=on_change,
                        allow_unset=(spec.default == ""),
                        labels=spec.choice_labels)


@register("list")
def _list(spec, on_change, choices, **_) -> Gtk.Widget:
    return ListEditor(on_change=on_change)


@register("cores")
def _cores(spec, on_change, choices, **_) -> Gtk.Widget:
    available = list(choices) if choices is not None else list(spec.choices or [])
    return CoresEditor(cores=available, on_change=on_change)


def _entry(spec, on_change, choices, **_) -> Gtk.Widget:
    entry = Gtk.Entry(text=str(spec.default))
    entry.connect("changed", lambda *_: on_change())
    return entry


def build_widget(spec, on_change: Callable[[], None],
                 choices: Optional[List[str]] = None) -> Gtk.Widget:
    """Build the control registered for ``spec.type`` (entry as fallback)."""
    return _FACTORIES.get(spec.type, _entry)(spec, on_change, choices)
