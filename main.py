#!/usr/bin/env python3
"""Entry point of the GameMode GUI.

The application modules (``core``, ``ui``, ``initializer``, ``sections/``, ...)
live in this repository root, so it is enough to run this file.

Run:                 python3 main.py
For a writable test: GAMEMODE_CONFIG=/tmp/try/gamemode.ini python3 main.py
"""

from __future__ import annotations

import sys


def main() -> int:
    from ui import run
    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
