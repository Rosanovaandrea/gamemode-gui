"""Small file helpers."""

from __future__ import annotations

import os
from typing import Optional


def read_text(path: Optional[str]) -> str:
    """Read a text file; missing or unreadable files yield ``""``."""
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            pass
    return ""
