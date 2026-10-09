#!/usr/bin/env python3
"""Entry point of the GameMode GUI.

The application is split into a few files, as required by the refactoring:

    main.py        -> this file: starts the application (delegates to ui.main())
    options.json   -> all options per category (data-driven)
    presentation.json -> content of the Presentation tab (data-driven)
    core.py        -> all the logic (definitions, special values, renderer,
                      config, i18n, utilities)
    ui.py          -> the whole GTK interface (tabs generated from the data)
    widgets.py     -> reusable widgets (build_widget + components)
    privileged.py  -> helper run as root to write into /etc
    fileops.py     -> atomic write/backup/rollback (GUI + root)
    style.css      -> app style (CSS loaded at runtime)
    locale/<lang>.xml -> translations (Italian and English)

Run with:  python3 main.py
For tests force a writable path:
    GAMEMODE_CONFIG=/tmp/try/gamemode.ini python3 main.py
"""

from __future__ import annotations

import sys


def main() -> int:
    from ui import main as _ui_main
    return _ui_main()


if __name__ == "__main__":
    sys.exit(main())
