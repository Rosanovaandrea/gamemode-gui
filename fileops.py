"""Operazioni atomiche sui file di configurazione, condivise.

Nessuna dipendenza da ``core.py`` o da GTK: questo modulo può essere importato
sia dalla GUI (percorso locale scrivibile) sia dall'helper privilegiato
``privileged.py`` (eseguito come root via pkexec/sudo).

Strategia "copy on write" per un commit sicuro:
    1. contenuto nuovo su ``<target>.tmp`` + ``fsync``;
    2. ``<target>.orig`` = copia "vergine" iniziale (creata una sola volta);
    3. ``<target>.bak`` = copia del file attivo precedente al commit;
    4. ``os.replace(tmp, target)`` (atomico su POSIX);
    5. su errore al passo 4: rollback automatico dal ``.bak``.

Le funzioni sono pure rispetto allo stato dell'app (nessuna classe): chi le usa
decide *dove* scrivere, qui c'è solo il *come* scrivere in modo sicuro.
"""

from __future__ import annotations

import os
import shutil
import tempfile


def _write_ephemeral(content: str) -> str:
    """Scrive ``content`` su un file temporaneo e ne restituisce il percorso."""
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


def ensure_orig(target: str, seed_content: str | None = None,
                fallback_path: str | None = None) -> None:
    """Crea ``<target>.orig`` se non esiste ancora (una sola volta in assoluto).

    Ordine di priorità per il contenuto "vergine":
      1. il file attivo ``target`` se esiste;
      2. ``seed_content`` (contenuto fornito dal chiamante);
      3. ``fallback_path`` (es. il ``.tmp`` appena scritto).
    """
    orig = target + ".orig"
    if os.path.exists(orig):
        return

    ephemeral = None
    if os.path.isfile(target):
        source = target
    elif seed_content is not None:
        source = ephemeral = _write_ephemeral(seed_content)
    elif fallback_path and os.path.isfile(fallback_path):
        source = fallback_path
    else:
        return

    try:
        shutil.copy2(source, orig)
        os.chmod(orig, 0o644)
    finally:
        if ephemeral is not None:
            try:
                os.remove(ephemeral)
            except OSError:
                pass


def write_commit(target: str, content: str, orig_seed_content: str | None = None,
                 create_dirs: bool = False) -> None:
    """Esegue un commit atomico di ``content`` su ``target``.

    Se ``create_dirs`` è True crea la cartella di destinazione (percorsi utente
    tipo ``~/.config``); per ``/etc`` la cartella esiste già.
    """
    if create_dirs:
        directory = os.path.dirname(target) or "."
        os.makedirs(directory, mode=0o700, exist_ok=True)

    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o644)

    # Un seed vuoto equivale a "nessun seed": si usa il contenuto appena scritto.
    ensure_orig(target, seed_content=(orig_seed_content or None), fallback_path=tmp)

    had_previous = os.path.isfile(target)
    if had_previous:
        shutil.copy2(target, target + ".bak")

    try:
        os.replace(tmp, target)
    except OSError:
        if had_previous and os.path.isfile(target + ".bak"):
            shutil.copy2(target + ".bak", target)
        raise

    os.chmod(target, 0o644)

    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass


def restore_from_backup(target: str) -> None:
    """Ripristina ``<target>.bak`` -> ``target``."""
    backup = target + ".bak"
    if not os.path.isfile(backup):
        raise FileNotFoundError("nessun backup disponibile")
    shutil.copy2(backup, target)
    os.chmod(target, 0o644)


def restore_from_orig(target: str) -> None:
    """Ripristina ``<target>.orig`` -> ``target``."""
    orig = target + ".orig"
    if not os.path.isfile(orig):
        raise FileNotFoundError("nessun originale disponibile")
    shutil.copy2(orig, target)
    os.chmod(target, 0o644)
