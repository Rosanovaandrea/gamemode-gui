#!/usr/bin/env python3
"""Entry point della GUI di GameMode.

L'applicazione è divisa in pochi file, come richiesto nel refactoring:

    main.py   → questo file: avvia l'applicazione (delega a ui.main())
    core.py   → tutta la logica (tabella, renderer, config, i18n, utility)
    ui.py     → tutta l'interfaccia GTK (divisa per step)
    privileged.py → helper eseguito come root per scrivere in /etc
    locale/<lang>.xml → traduzioni (oggi solo italiano, configurabile)

Lanciare con:  python3 main.py
Per i test forzare un percorso scrivibile:
    GAMEMODE_CONFIG=/tmp/prova/gamemode.ini python3 main.py
"""

from __future__ import annotations

import sys


def main() -> int:
    from ui import main as _ui_main
    return _ui_main()


if __name__ == "__main__":
    sys.exit(main())