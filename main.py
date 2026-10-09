#!/usr/bin/env python3
"""Entry point della GUI di GameMode.

L'applicazione è divisa in pochi file, come richiesto nel refactoring:

    main.py        → questo file: avvia l'applicazione (delega a ui.main())
    options.json   → tutte le opzioni per categoria (data-driven)
    core.py        → tutta la logica (definizioni, valori speciali, renderer,
                     config, i18n, utility)
    ui.py          → tutta l'interfaccia GTK (schede generate dai dati)
    widgets.py     → widget riutilizzabili (build_widget + componenti)
    privileged.py  → helper eseguito come root per scrivere in /etc
    fileops.py     → scrittura atomica/backup/rollback (GUI + root)
    style.css      → stile dell'app (CSS caricato a runtime)
    locale/<lang>.xml → traduzioni (italiano e inglese)

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