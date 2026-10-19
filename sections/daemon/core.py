"""GameMode daemon actions (diagnostics, version, restart and group)."""

from __future__ import annotations

import getpass
import grp
from typing import Optional

from i18n.translator import tr

from services.commands import (
    CommandResult, find_executable, privileged_prefixes, run_command,
)

GAMEMODED = "gamemoded"
GAMEMODED_PATHS = ("/usr/bin/gamemoded", "/usr/local/bin/gamemoded")
SYSTEMCTL = "systemctl"
SYSTEMCTL_PATHS = ("/usr/bin/systemctl", "/bin/systemctl")
PKILL = "pkill"
PKILL_PATHS = ("/usr/bin/pkill", "/bin/pkill")
USERMOD = "usermod"
USERMOD_PATHS = ("/usr/sbin/usermod", "/sbin/usermod")
GAMEMODE_GROUP = "gamemode"

TEST_ARGS = ("-t",)
VERSION_ARGS = ("--version",)
SYSTEMCTL_USER_RESTART_ARGS = ("--user", "restart", GAMEMODED)
SYSTEMCTL_RESTART_ARGS = ("restart", GAMEMODED)
PKILL_ARGS = ("-TERM", GAMEMODED)
USERMOD_GROUP_ARGS = ("-aG", GAMEMODE_GROUP)

TEST_COMMAND = f"{GAMEMODED} {' '.join(TEST_ARGS)}"
VERSION_COMMAND = f"{GAMEMODED} {' '.join(VERSION_ARGS)}"
RESTART_COMMAND = f"{SYSTEMCTL} {' '.join(SYSTEMCTL_USER_RESTART_ARGS)}"
GROUP_COMMAND = f"{USERMOD} {' '.join(USERMOD_GROUP_ARGS)} {{user}}"


def test_daemon() -> CommandResult:
    """Run the daemon diagnostic tests (``gamemoded -t``)."""
    gamemoded = find_executable(GAMEMODED, *GAMEMODED_PATHS)
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command=TEST_COMMAND)
    return run_command([gamemoded, *TEST_ARGS])


def daemon_version() -> CommandResult:
    """GameMode version (``gamemoded --version``)."""
    gamemoded = find_executable(GAMEMODED, *GAMEMODED_PATHS)
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command=VERSION_COMMAND)
    return run_command([gamemoded, *VERSION_ARGS])


def restart_daemon() -> CommandResult:
    """Restart gamemoded via the user unit, the system unit, or ``pkill``."""
    systemctl = find_executable(SYSTEMCTL, *SYSTEMCTL_PATHS)
    if systemctl:
        user_result = run_command([systemctl, *SYSTEMCTL_USER_RESTART_ARGS])
        if user_result.success:
            return user_result
        system_result = run_command([systemctl, *SYSTEMCTL_RESTART_ARGS])
        return system_result if system_result.success else user_result
    pkill = find_executable(PKILL, *PKILL_PATHS)
    if pkill:
        return run_command([pkill, *PKILL_ARGS])
    return CommandResult(False, -1, error=tr("msg.no_systemd"))


def group_exists() -> bool:
    """True if the ``gamemode`` group exists."""
    try:
        grp.getgrnam(GAMEMODE_GROUP)
        return True
    except KeyError:
        return False


def user_in_group(user: Optional[str] = None) -> bool:
    """True if the user (default: current) belongs to ``gamemode``."""
    user = user or getpass.getuser()
    if not group_exists():
        return False
    return user in list(grp.getgrnam(GAMEMODE_GROUP).gr_mem)


def add_user_to_group() -> CommandResult:
    """Add the current user to the ``gamemode`` group."""
    user = getpass.getuser()
    usermod = find_executable(USERMOD, *USERMOD_PATHS)
    if not usermod:
        return CommandResult(False, -1, error=tr("msg.usermod_missing"),
                             command=GROUP_COMMAND.format(user=user))
    argv = [usermod, *USERMOD_GROUP_ARGS, user]
    last_result = CommandResult(False, -1, error=tr("msg.no_priv_frontend"),
                                command=" ".join(argv))
    for prefix in privileged_prefixes():
        result = run_command(prefix + argv, timeout=60)
        if result.success:
            return result
        last_result = result
    return last_result
