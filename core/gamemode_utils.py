"""Helpers for interacting with the GameMode daemon, the user group and the
systemd user service.

All privileged commands run through ``pkexec`` (or fall back to ``sudo``)
and never use a shell.
"""

from __future__ import annotations

import getpass
import grp
import os
import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class CommandResult:
    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""

    @property
    def output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout.rstrip())
        if self.stderr:
            parts.append(self.stderr.rstrip())
        if self.error:
            parts.append(self.error)
        return "\n".join(parts)


def _run(argv: List[str], timeout: int = 30) -> CommandResult:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            success=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except FileNotFoundError as exc:
        return CommandResult(False, -1, error=f"Comando non trovato: {exc}")
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            False, -1, error=f"Timeout dopo {timeout}s",
            stdout=exc.stdout or "", stderr=exc.stderr or "",
        )
    except OSError as exc:
        return CommandResult(False, -1, error=str(exc))


def test_daemon() -> CommandResult:
    return _run(["gamemoded", "-t"])


def daemon_version() -> CommandResult:
    return _run(["gamemoderun", "--version"])


def restart_daemon() -> CommandResult:
    return _run(["systemctl", "--user", "restart", "gamemoded"])


def group_exists() -> bool:
    try:
        grp.getgrnam("gamemode")
        return True
    except KeyError:
        return False


def user_in_group(user: str | None = None) -> bool:
    user = user or getpass.getuser()
    if not group_exists():
        return False
    members = list(grp.getgrnam("gamemode").gr_mem)
    return user in members


def add_user_to_group() -> CommandResult:
    """Add the current user to the ``gamemode`` group via a privileged helper."""
    user = getpass.getuser()
    argv = ["usermod", "-aG", "gamemode", user]
    # Prefer a graphical polkit prompt when available.
    for prefix in (["pkexec"], ["sudo", "-n"]):
        try:
            res = _run(prefix + argv, timeout=60)
        except subprocess.SubprocessError:
            res = CommandResult(False, -1, error="Esecuzione privilegiata fallita")
        return res
    return CommandResult(False, -1, error="Nessun frontend privilegiato disponibile")