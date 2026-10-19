#!/usr/bin/env python3
"""Privileged helper for operations on /etc/gamemode.ini.

This module is run AS ROOT via ``pkexec`` (or the ``sudo`` fallback) by the GUI.
It must not be imported directly by the app: it is a standalone command invoked
with subprocess.

Why does it exist?
    The file we manage lives in ``/etc`` (root-owned). The GUI runs as a normal
    user, so all *writes* (tmp, backup, replace, rollback) must happen in a
    privileged process.

The atomic write/backup/rollback logic is NOT here: it lives in
``configuration.py``, shared with the GUI's local path. This file only handles
command-line parsing and stdin I/O.

Commands:
    commit <path> [seed]     rewrite the file reading the content from stdin.
                             ``seed`` is the optional path of a file with the
                             "pristine" content to use for ``.orig``.
    restore-backup <path>    restore ``.bak`` -> active file.
    restore-orig <path>      restore ``.orig`` -> active file.
    ensure-orig <path>       create ``.orig`` if missing (stdin = default content
                             to use when the file does not exist).

Managed files (all next to <path>):
    <path>.tmp   new content, not yet committed
    <path>.bak   copy of the active file before the commit
    <path>.orig  initial "pristine" copy (never rewritten automatically)
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from configuration import (
    ensure_orig, restore_from_backup, restore_from_orig, write_commit,
)
from services.privileged import (
    COMMAND_COMMIT, COMMAND_ENSURE_ORIG, COMMAND_RESTORE_BACKUP, COMMAND_RESTORE_ORIG,
)

USAGE = (f"usage: privileged_helper.py <{COMMAND_COMMIT}|{COMMAND_RESTORE_BACKUP}|"
         f"{COMMAND_RESTORE_ORIG}|{COMMAND_ENSURE_ORIG}> <path> [seed]\n")


def _read_seed(path: str | None) -> str | None:
    """Read the "seed" file (pristine content) if given, otherwise None."""
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(USAGE)
        return 2

    command, target = argv[0], argv[1]

    try:
        match command:
            case _ if command == COMMAND_COMMIT:
                content = sys.stdin.read()
                seed_path = argv[2] if len(argv) > 2 else None
                write_commit(target, content,
                             orig_seed_content=_read_seed(seed_path))
            case _ if command == COMMAND_RESTORE_BACKUP:
                restore_from_backup(target)
            case _ if command == COMMAND_RESTORE_ORIG:
                restore_from_orig(target)
            case _ if command == COMMAND_ENSURE_ORIG:
                ensure_orig(target, seed_content=sys.stdin.read())
            case _:
                sys.stderr.write(f"unknown command: {command}\n")
                return 2
        sys.stdout.write("ok\n")
    except OSError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
