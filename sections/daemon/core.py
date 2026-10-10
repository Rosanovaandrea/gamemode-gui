"""Core of the Daemon section (stateless).

Side-effecting system calls for the daemon tab: run the diagnostics, read the
version, restart the daemon and manage the ``gamemode`` group. They are kept out
of the view so the UI only triggers actions and renders their output.
"""

from __future__ import annotations

import getpass
import grp
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from i18n import tr


def test_daemon() -> CommandResult:
    """Run the daemon diagnostic tests (``gamemoded -t``)."""
    # Locate gamemoded; if it is not installed there is nothing to test.
    gamemoded = find_executable("gamemoded", "/usr/bin/gamemoded",
                                "/usr/local/bin/gamemoded")
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command="gamemoded -t")
    return run_command([gamemoded, "-t"])


def daemon_version() -> CommandResult:
    """GameMode version (``gamemoded --version``).

    ``gamemoderun --version`` is not used: ``gamemoderun`` execs the passed
    command with LD_PRELOAD and does not handle ``--version``.
    """
    # The version is printed by gamemoded, not by the gamemoderun wrapper.
    gamemoded = find_executable("gamemoded", "/usr/bin/gamemoded",
                                "/usr/local/bin/gamemoded")
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command="gamemoded --version")
    return run_command([gamemoded, "--version"])


def restart_daemon() -> CommandResult:
    """Restart gamemoded, trying the user unit, then the system unit, then pkill.

    GameMode installs ``gamemoded.service`` as a systemd **user** unit. Without
    systemd the daemon is D-Bus activated and restarts on the next request, so a
    ``pkill`` is enough.
    """
    systemctl = find_executable("systemctl", "/usr/bin/systemctl", "/bin/systemctl")
    if systemctl:
        user_result = run_command([systemctl, "--user", "restart", "gamemoded"])
        if user_result.success:
            return user_result
        system_result = run_command([systemctl, "restart", "gamemoded"])
        return system_result if system_result.success else user_result
    pkill = find_executable("pkill", "/usr/bin/pkill", "/bin/pkill")
    if pkill:
        return run_command([pkill, "-TERM", "gamemoded"])
    return CommandResult(False, -1, error=tr("msg.no_systemd"))


def group_exists() -> bool:
    """True if the ``gamemode`` group exists on the system."""
    try:
        grp.getgrnam("gamemode")
        return True
    except KeyError:
        return False


def user_in_group(user: Optional[str] = None) -> bool:
    """True if the given user (default: current) belongs to ``gamemode``."""
    user = user or getpass.getuser()
    if not group_exists():
        return False
    return user in list(grp.getgrnam("gamemode").gr_mem)


def add_user_to_group() -> CommandResult:
    """Add the current user to the ``gamemode`` group (``usermod -aG``)."""
    user = getpass.getuser()
    usermod = find_executable("usermod", "/usr/sbin/usermod", "/sbin/usermod")
    if not usermod:
        return CommandResult(False, -1, error=tr("msg.usermod_missing"),
                             command=f"usermod -aG gamemode {user}")
    argv = [usermod, "-aG", "gamemode", user]
    last_result = CommandResult(False, -1, error=tr("msg.no_priv_frontend"),
                                command=" ".join(argv))
    for prefix in privileged_prefixes():
        result = run_command(prefix + argv, timeout=60)
        if result.success:
            return result
        last_result = result
    return last_result


# --- local command helpers (owned by this section, not shared) ---------------

@dataclass
class CommandResult:
    """Outcome of an external command, with a combined ``output`` view."""

    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    command: str = ""

    @property
    def output(self) -> str:
        parts: List[str] = []
        if self.stdout:
            parts.append(self.stdout.rstrip())
        if self.stderr:
            parts.append(self.stderr.rstrip())
        if self.error:
            parts.append(self.error)
        return "\n".join(parts)


def find_executable(name: str, *fallbacks: str) -> Optional[str]:
    """Find an executable in PATH, then among the known absolute paths."""
    path = shutil.which(name)
    if path:
        return path
    for candidate in fallbacks:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def run_command(argv: List[str], timeout: int = 30) -> CommandResult:
    """Run a command capturing its output; never raises on failure."""
    command = " ".join(argv)
    try:
        process = subprocess.run(argv, capture_output=True, text=True,
                                 timeout=timeout, check=False)
        return CommandResult(process.returncode == 0, process.returncode,
                             process.stdout, process.stderr, command=command)
    except FileNotFoundError as exc:
        return CommandResult(False, -1, error=f"{tr('msg.cmd_not_found')}: {exc}",
                             command=command)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, -1, error=tr("msg.timeout"),
                             stdout=exc.stdout or "", stderr=exc.stderr or "",
                             command=command)
    except OSError as exc:
        return CommandResult(False, -1, error=str(exc), command=command)


def privileged_prefixes() -> List[List[str]]:
    """Available privileged prefixes, in order (pkexec, then sudo)."""
    prefixes: List[List[str]] = []
    pkexec = find_executable("pkexec", "/usr/bin/pkexec", "/usr/sbin/pkexec")
    if pkexec:
        prefixes.append([pkexec])
    sudo = find_executable("sudo", "/usr/bin/sudo", "/bin/sudo", "/usr/sbin/sudo")
    if sudo:
        prefixes.append([sudo, "-n"])
    return prefixes
