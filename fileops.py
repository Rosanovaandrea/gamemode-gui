"""Atomic configuration-file operations, shared.

No dependency on ``core.py`` or GTK: this module can be imported both by the GUI
(local writable path) and by the privileged helper ``privileged.py`` (run as root
via pkexec/sudo).

"Copy on write" strategy for a safe commit:
    1. new content to ``<target>.tmp`` + ``fsync``;
    2. ``<target>.orig`` = initial "pristine" copy (created only once);
    3. ``<target>.bak`` = copy of the active file before the commit;
    4. ``os.replace(tmp, target)`` (atomic on POSIX);
    5. on error at step 4: automatic rollback from ``.bak``.

The functions are pure with respect to the app state (no class): the caller
decides *where* to write, here there is only *how* to write safely.
"""

from __future__ import annotations

import os
import shutil
import tempfile


def _write_ephemeral(content: str) -> str:
    """Write ``content`` to a temporary file and return its path."""
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
    """Create ``<target>.orig`` if it does not exist yet (once and for all).

    Priority order for the "pristine" content:
      1. the active file ``target`` if it exists;
      2. ``seed_content`` (content provided by the caller);
      3. ``fallback_path`` (e.g. the ``.tmp`` just written).
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
    """Perform an atomic commit of ``content`` to ``target``.

    If ``create_dirs`` is True, create the destination folder (user paths such as
    ``~/.config``); for ``/etc`` the folder already exists.
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

    # An empty seed is equivalent to "no seed": use the content just written.
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
    """Restore ``<target>.bak`` -> ``target``."""
    backup = target + ".bak"
    if not os.path.isfile(backup):
        raise FileNotFoundError("no backup available")
    shutil.copy2(backup, target)
    os.chmod(target, 0o644)


def restore_from_orig(target: str) -> None:
    """Restore ``<target>.orig`` -> ``target``."""
    orig = target + ".orig"
    if not os.path.isfile(orig):
        raise FileNotFoundError("no original available")
    shutil.copy2(orig, target)
    os.chmod(target, 0o644)
