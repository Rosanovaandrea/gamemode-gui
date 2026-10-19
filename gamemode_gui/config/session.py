"""JSON sidecar with the last saved values."""

from __future__ import annotations

import json
from typing import Dict, Optional


def session_path(config_path: str) -> str:
    return config_path + ".session.json"


def save_session(config_path: str, values: Dict[str, object]) -> None:
    """Persist the current values to ``<config>.session.json`` (best effort)."""
    categories: Dict[str, Dict[str, object]] = {}
    for flat_key, value in values.items():
        section, _, key = flat_key.partition(".")
        categories.setdefault(section, {})[key] = value
    try:
        with open(session_path(config_path), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "categories": categories}, handle, indent=2)
    except OSError:
        pass


def load_session(config_path: str) -> Optional[Dict[str, object]]:
    """Load the flat ``section.key -> value`` mapping from the session JSON."""
    try:
        with open(session_path(config_path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    categories = data.get("categories")
    if isinstance(categories, dict):
        flat: Dict[str, object] = {}
        for section, options in categories.items():
            if isinstance(options, dict):
                for key, value in options.items():
                    flat[f"{section}.{key}"] = value
        return flat
    return data.get("values") if isinstance(data.get("values"), dict) else None
