"""Helpers shared by the section integration tests.

Each test is a plain script (``python3 test/sections/test_<section>.py``) covering
one section's happy path plus the paths that can go wrong. This module keeps them
short: it makes the application modules importable, isolates the process from the
real configuration and user settings, and collects simple pass/fail checks.
"""

from __future__ import annotations

import os
import sys
import tempfile

# The application modules live at the repository root (two levels up).
APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_checks = []


def isolate() -> str:
    """Point the app at throwaway paths and return the work directory.

    Call it *before* importing the application modules: the real ``/etc``
    configuration and the user settings must never be touched.
    """
    work_dir = tempfile.mkdtemp(prefix="gamemodegui_section_")
    os.environ["GAMEMODE_CONFIG"] = os.path.join(work_dir, "etc", "gamemode.ini")
    os.environ["GAMEMODE_BASE"] = ""            # pretend nothing is installed
    os.environ["XDG_CONFIG_HOME"] = os.path.join(work_dir, "config")
    os.environ["HOME"] = os.path.join(work_dir, "home")
    for path in (os.path.dirname(os.environ["GAMEMODE_CONFIG"]),
                 os.environ["XDG_CONFIG_HOME"], os.environ["HOME"]):
        os.makedirs(path, exist_ok=True)
    return work_dir


def option_in(core, key: str):
    """The option descriptor named ``key`` inside a section core."""
    return next(option for option in core.options if option.key == key)


def check(label: str, condition: object) -> None:
    """Record and print one named check."""
    ok = bool(condition)
    _checks.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


def equal(label: str, actual: object, expected: object) -> None:
    """Record a check that ``actual`` equals ``expected`` (showing both)."""
    ok = actual == expected
    detail = "" if ok else f"  (got {actual!r}, expected {expected!r})"
    _checks.append((label + detail, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {label}{detail}")


def finish() -> None:
    """Print the summary and exit non-zero if any check failed."""
    failed = [label for label, ok in _checks if not ok]
    print()
    if failed:
        print(f"FAILED: {len(failed)} of {len(_checks)} checks")
        for label in failed:
            print(f"  - {label}")
        sys.exit(1)
    print(f"OK: {len(_checks)} checks passed")
