#!/usr/bin/env python3
"""Helper privilegiato per le operazioni su /etc/gamemode.ini.

Questo modulo viene eseguito COME ROOT tramite ``pkexec`` (oppure fallback
``sudo``) dalla GUI. Non deve essere importato direttamente dall'app: è un
comando a sé stante invocato con subprocess.

Perché esiste?
    Il file che vogliamo gestire vive in ``/etc`` (root-owned). La GUI gira
    come utente normale, quindi tutte le *scritture* (tmp, backup, replace,
    rollback) devono avvenire in un processo privilegiato.

La logica di scrittura atomica/backup/rollback NON è qui: sta in ``fileops.py``,
condivisa con il percorso locale della GUI. Questo file si occupa solo del
parsing della riga di comando e dell'I/O da stdin.

Comandi:
    commit <path> [seed]     riscrive il file leggendo il contenuto da stdin.
                             ``seed`` è il percorso opzionale di un file con il
                             contenuto "vergine" da usare per ``.orig``.
    restore-backup <path>    ripristina ``.bak`` -> file attivo.
    restore-orig <path>      ripristina ``.orig`` -> file attivo.
    ensure-orig <path>       crea ``.orig`` se assente (stdin = contenuto di
                             default da usare quando il file non esiste).

File gestiti (tutti accanto a <path>):
    <path>.tmp   contenuto nuovo, non ancora committato
    <path>.bak   copia del file attivo precedente al commit
    <path>.orig  copia iniziale "vergine" (mai riscritta automaticamente)
"""

from __future__ import annotations

import sys

import fileops


def _read_seed(path: str | None) -> str | None:
    """Legge il file "seed" (contenuto vergine) se indicato, altrimenti None."""
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(
            "uso: privileged.py <commit|restore-backup|restore-orig|ensure-orig> <path> [seed]\n")
        return 2

    command, target = argv[0], argv[1]

    try:
        if command == "commit":
            content = sys.stdin.read()
            seed_path = argv[2] if len(argv) > 2 else None
            fileops.write_commit(target, content,
                                 orig_seed_content=_read_seed(seed_path))
            sys.stdout.write("ok\n")
        elif command == "restore-backup":
            fileops.restore_from_backup(target)
            sys.stdout.write("ok\n")
        elif command == "restore-orig":
            fileops.restore_from_orig(target)
            sys.stdout.write("ok\n")
        elif command == "ensure-orig":
            content = sys.stdin.read()
            fileops.ensure_orig(target, seed_content=content)
            sys.stdout.write("ok\n")
        else:
            sys.stderr.write(f"comando sconosciuto: {command}\n")
            return 2
    except OSError as exc:
        sys.stderr.write(f"errore: {exc}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"errore: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
