#!/usr/bin/env python3
"""Entry point of the GameMode GUI."""

from __future__ import annotations

import sys


def main() -> int:
    from gamemode_gui.ui.window import run
    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
