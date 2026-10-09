#!/usr/bin/env python3
"""Privileged helper for operations on /etc/gamemode.ini.

This module is run AS ROOT via ``pkexec`` (or the ``sudo`` fallback) by the GUI.
It must not be imported directly by the app: it is a standalone command invoked
with subprocess.

Why does it exist?
    The file we manage lives in ``/etc`` (root-owned). The GUI runs as a normal
    user, so all *writes* (tmp, backup, replace, rollback) must happen in a
    privileged process.

The atomic write/backup/rollback logic is NOT here: it lives in ``fileops.py``,
shared with the GUI's local path. This file only handles command-line parsing and
stdin I/O.

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

import sys

import fileops


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
        sys.stderr.write(
            "usage: privileged.py <commit|restore-backup|restore-orig|ensure-orig> <path> [seed]\n")
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
            sys.stderr.write(f"unknown command: {command}\n")
            return 2
    except OSError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
