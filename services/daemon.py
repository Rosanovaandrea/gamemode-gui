"""GameMode daemon actions (diagnostics, version, restart and group)."""

from __future__ import annotations

import getpass
import grp
from typing import Optional

from i18n.translator import tr

from .commands import CommandResult, find_executable, privileged_prefixes, run_command


def test_daemon() -> CommandResult:
    """Run the daemon diagnostic tests (``gamemoded -t``)."""
    gamemoded = find_executable("gamemoded", "/usr/bin/gamemoded",
                                "/usr/local/bin/gamemoded")
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command="gamemoded -t")
    return run_command([gamemoded, "-t"])


def daemon_version() -> CommandResult:
    """GameMode version (``gamemoded --version``)."""
    gamemoded = find_executable("gamemoded", "/usr/bin/gamemoded",
                                "/usr/local/bin/gamemoded")
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command="gamemoded --version")
    return run_command([gamemoded, "--version"])


def restart_daemon() -> CommandResult:
    """Restart gamemoded via the user unit, the system unit, or ``pkill``."""
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
    """True if the ``gamemode`` group exists."""
    try:
        grp.getgrnam("gamemode")
        return True
    except KeyError:
        return False


def user_in_group(user: Optional[str] = None) -> bool:
    """True if the user (default: current) belongs to ``gamemode``."""
    user = user or getpass.getuser()
    if not group_exists():
        return False
    return user in list(grp.getgrnam("gamemode").gr_mem)


def add_user_to_group() -> CommandResult:
    """Add the current user to the ``gamemode`` group."""
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
