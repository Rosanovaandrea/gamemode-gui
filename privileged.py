#!/usr/bin/env python3
"""Helper privilegiato per le operazioni su /etc/gamemode.ini.

Questo modulo viene eseguito COME ROOT tramite ``pkexec`` (oppure fallback
``sudo``) dalla GUI. Non deve essere importato direttamente dall'app: è un
comando a sé stante invocato con subprocess.

Perché esiste?
    Il file che vogliamo gestire vive in ``/etc`` (root-owned). La GUI gira
    come utente normale, quindi tutte le *scritture* (tmp, backup, replace,
    rollback) devono avvenire in un processo privilegiato. Il costo è che si
    riscrive il file completo al commit (strategia "copy on write"): si scrive
    ``.tmp``, si fa ``fsync``, si copia il vecchio in ``.bak`` e infine si
    ``os.replace(tmp, target)`` che è atomico su POSIX.

Comandi:
    commit <path>                riscrive il file leggendo il contenuto da stdin.
                                 Garantisce anche la creazione di ``.orig`` (una
                                 sola volta) e del ``.bak`` (precedente).
    restore-backup <path>        ripristina ``.bak`` -> file attivo.
    restore-orig <path>          ripristina ``.orig`` -> file attivo.
    ensure-orig <path>           crea ``.orig`` se assente (stdin = contenuto di
                                 default da usare quando il file non esiste).

File gestiti (tutti accanto a <path>):
    <path>.tmp   contenuto nuovo, non ancora committato
    <path>.bak   copia del file attivo precedente al commit
    <path>.orig  copia iniziale "vergine" (mai riscritta automaticamente)

La regola pratica: se l'operazione fallisce a metà (es. errore io su replace),
il comando tenta di ripristinare il ``.bak`` e termina con exit code != 0.
"""

from __future__ import annotations

import os
import shutil
import sys


# ---------------------------------------------------------------------------
# Operazioni di base (indipendenti dal fatto che si esegua come root)
# ---------------------------------------------------------------------------
def _fsync_file(path: str) -> None:
    with open(path, "rb") as fh:
        os.fsync(fh.fileno())


def write_new_commit(target: str, content: str) -> None:
    """Esegue un commit atomico di ``content`` su ``target``.

    Sequenza (allineata alla specifica):
      1. scrivi ``target.tmp`` + fsync
      2. se ``target`` esiste, copia in ``target.bak``
      3. ``os.replace(tmp, target)``  -> atomico
      4. chmod 0644 sul file attivo
      5. pulizia eventuale tmp residuo

    Su errore al passo 3 il ``.bak`` viene ripristinato automaticamente.
    """
    tmp = target + ".tmp"

    # 1. contenuto nuovo su file temporaneo, sincronizzato su disco
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o644)

    # 2. "orig" = stato iniziale, creato UNA sola volta, mai ritoccato.
    #    Se il file attivo esiste lo copiamo; se non esiste (primo avvio) lo
    #    inizializziamo con il contenuto che stiamo per scrivere.
    _ensure_orig(target, tmp)

    # 3. backup del file attivo precedente (il "prima" del commit)
    had_previous = os.path.isfile(target)
    if had_previous:
        shutil.copy2(target, target + ".bak")

    # 4. commit atomico
    try:
        os.replace(tmp, target)
    except OSError:
        # rollback automatico: ripristina il file precedente dal backup
        if had_previous and os.path.isfile(target + ".bak"):
            shutil.copy2(target + ".bak", target)
        raise

    os.chmod(target, 0o644)

    # 5. pulizia residui
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass


def _ensure_orig(target: str, new_content_path: str) -> None:
    """Crea ``<target>.orig`` se non esiste ancora (una volta in assoluto)."""
    orig = target + ".orig"
    if os.path.exists(orig):
        return
    source = target if os.path.isfile(target) else new_content_path
    shutil.copy2(source, orig)
    os.chmod(orig, 0o644)


def restore_from_backup(target: str) -> None:
    if not os.path.isfile(target + ".bak"):
        raise FileNotFoundError("nessun backup disponibile")
    shutil.copy2(target + ".bak", target)
    os.chmod(target, 0o644)


def restore_from_orig(target: str) -> None:
    if not os.path.isfile(target + ".orig"):
        raise FileNotFoundError("nessun originale disponibile")
    shutil.copy2(target + ".orig", target)
    os.chmod(target, 0o644)


def ensure_orig(target: str, default_content: str) -> None:
    """Crea ``.orig`` da un contenuto di default (usato solo in assenza del
    file attivo, tipicamente al primo avvio dell'applicazione)."""
    if os.path.exists(target + ".orig"):
        return
    source = target if os.path.isfile(target) else _write_ephemeral(default_content)
    shutil.copy2(source, target + ".orig")
    os.chmod(target + ".orig", 0o644)


def _write_ephemeral(content: str) -> str:
    import tempfile
    fd, path = tempfile.mkstemp(prefix="gamemode-orig-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        os.unlink(path)
        raise
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("uso: privileged.py <commit|restore-backup|restore-orig|ensure-orig> <path> [--] \n")
        return 2

    command, target = argv[0], argv[1]

    try:
        if command == "commit":
            content = sys.stdin.read()
            write_new_commit(target, content)
            sys.stdout.write("ok\n")
        elif command == "restore-backup":
            restore_from_backup(target)
            sys.stdout.write("ok\n")
        elif command == "restore-orig":
            restore_from_orig(target)
            sys.stdout.write("ok\n")
        elif command == "ensure-orig":
            content = sys.stdin.read()
            ensure_orig(target, content)
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