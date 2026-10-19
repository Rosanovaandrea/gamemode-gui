"""Privileged operations on ``/etc/gamemode.ini``."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional

from .commands import CommandResult, privileged_prefixes


def run_privileged(command: str, path: str, content: str = "", timeout: int = 60,
                   extra_args: Optional[List[str]] = None) -> CommandResult:
    """Run the root helper, trying pkexec then sudo."""
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "privileged_helper.py")
    helper_argv = [sys.executable, helper, command, path] + list(extra_args or [])
    for prefix in privileged_prefixes():
        try:
            process = subprocess.run(prefix + helper_argv, input=content,
                                     capture_output=True, text=True,
                                     timeout=timeout, check=False)
            return CommandResult(process.returncode == 0, process.returncode,
                                 process.stdout, process.stderr,
                                 command=" ".join(prefix + helper_argv))
        except (FileNotFoundError, subprocess.SubprocessError):
            continue
    raise FileNotFoundError("no privileged frontend available (pkexec/sudo)")


def is_privileged_path(path: str) -> bool:
    """True if the destination directory is not writable by the user."""
    return not os.access(os.path.dirname(path) or "/", os.W_OK)
