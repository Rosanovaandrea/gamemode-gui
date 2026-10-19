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

Every file that must be *placed* next to ``<target>`` (``.tmp``, ``.orig``,
``.bak``) and every restore goes through the same primitive: write the bytes to
a temporary file **in the same directory**, ``fsync``, then ``os.replace`` into
place. ``os.replace`` is a rename and is atomic on POSIX, so a reader — or a
crash in the middle — never sees a half-written file. That is why ``shutil`` is
not used for the final placement: copying in place would leave a truncated
``.orig``/``.bak``/``target`` if interrupted.

The functions are pure with respect to the app state (no class): the caller
decides *where* to write, here there is only *how* to write safely.
"""

from __future__ import annotations

import os
import tempfile

_CHUNK_SIZE = 1 << 16
_FILE_MODE = 0o644


def _fsync_dir(directory: str) -> None:
    """Best-effort ``fsync`` of ``directory`` so a rename survives a crash."""
    try:
        dfd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dfd)
    except OSError:
        pass
    finally:
        os.close(dfd)


def _atomic_replace(dst: str, producer) -> None:
    """Atomically create/replace ``dst`` with what ``producer(fh)`` writes.

    The temporary file is created in the destination directory (same filesystem,
    so the final ``os.replace`` is a real rename and cannot fall back to a copy),
    flushed to disk and then moved into place. On any error the temp is removed.
    """
    directory = os.path.dirname(dst) or "."
    fd, tmp = tempfile.mkstemp(prefix=".gamemode-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as fh:
            producer(fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, _FILE_MODE)
        os.replace(tmp, dst)
        _fsync_dir(directory)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _atomic_copy(src: str, dst: str) -> None:
    """Atomically create/replace ``dst`` with a copy of the file ``src``.

    ``src`` is left untouched (it may be ``target`` itself, or a ``.bak``/``.orig``
    that must survive); only the final destination is swapped in.
    """
    def _producer(fh) -> None:
        with open(src, "rb") as source:
            for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                fh.write(chunk)

    _atomic_replace(dst, _producer)


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

    if os.path.isfile(target):
        _atomic_copy(target, orig)
    elif seed_content is not None:
        # Write the caller-provided seed as the pristine content (atomic).
        _atomic_replace(orig, lambda handle: handle.write(seed_content.encode("utf-8")))
    elif fallback_path and os.path.isfile(fallback_path):
        _atomic_copy(fallback_path, orig)


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
    # Write the new content to the temp file (atomic: temp file + os.replace).
    _atomic_replace(tmp, lambda handle: handle.write(content.encode("utf-8")))

    # An empty seed is equivalent to "no seed": use the content just written.
    ensure_orig(target, seed_content=(orig_seed_content or None), fallback_path=tmp)

    had_previous = os.path.isfile(target)
    if had_previous:
        # Atomic: ``.bak`` is never left half-written, so a rollback can trust it.
        _atomic_copy(target, target + ".bak")

    try:
        os.replace(tmp, target)
    except OSError:
        if had_previous and os.path.isfile(target + ".bak"):
            _atomic_copy(target + ".bak", target)
        raise
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    os.chmod(target, _FILE_MODE)


def restore_from_backup(target: str) -> None:
    """Restore ``<target>.bak`` -> ``target`` (atomic)."""
    backup = target + ".bak"
    if not os.path.isfile(backup):
        raise FileNotFoundError("no backup available")
    _atomic_copy(backup, target)


def restore_from_orig(target: str) -> None:
    """Restore ``<target>.orig`` -> ``target`` (atomic)."""
    orig = target + ".orig"
    if not os.path.isfile(orig):
        raise FileNotFoundError("no original available")
    _atomic_copy(orig, target)
