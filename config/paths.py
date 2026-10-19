"""Configuration paths."""

from __future__ import annotations

import os
from typing import Optional


def resolve_config_path() -> str:
    """Path managed by the GUI (``GAMEMODE_CONFIG`` or ``/etc/gamemode.ini``)."""
    return os.environ.get("GAMEMODE_CONFIG") or "/etc/gamemode.ini"


def resolve_base_path() -> Optional[str]:
    """Find the package-installed gamemode.ini, or ``None``."""
    if "GAMEMODE_BASE" in os.environ:
        return os.environ.get("GAMEMODE_BASE", "").strip() or None
    xdg = os.environ.get("XDG_DATA_DIRS", "").strip()
    data_dirs = [d for d in xdg.split(":") if d] if xdg else []
    data_dirs += ["/usr/local/share", "/usr/share"]
    for data_dir in data_dirs:
        path = os.path.join(data_dir, "gamemode", "gamemode.ini")
        if os.path.isfile(path):
            return path
    return None
