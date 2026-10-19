"""External command helpers shared by the daemon and privileged services."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from i18n.translator import tr

PKEXEC = "pkexec"
PKEXEC_PATHS = ("/usr/bin/pkexec", "/usr/sbin/pkexec")
SUDO = "sudo"
SUDO_PATHS = ("/usr/bin/sudo", "/bin/sudo", "/usr/sbin/sudo")
SUDO_NONINTERACTIVE = "-n"


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
        streams = (self.stdout.rstrip(), self.stderr.rstrip(), self.error)
        return "\n".join(stream for stream in streams if stream)


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
    pkexec = find_executable(PKEXEC, *PKEXEC_PATHS)
    if pkexec:
        prefixes.append([pkexec])
    sudo = find_executable(SUDO, *SUDO_PATHS)
    if sudo:
        prefixes.append([sudo, SUDO_NONINTERACTIVE])
    return prefixes
