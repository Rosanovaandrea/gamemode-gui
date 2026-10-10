"""General core: orchestrates the sections and runs the app-wide operations.

It holds the section cores (each the source of truth for its own choices) and
does only three things:

  1. orchestrate the sections: it joins their own rendered output into the
     gamemode.ini content;
  2. manage the file: atomic save, restore previous (``.bak``) and factory reset
     (``.orig``), plus the JSON session sidecar;
  3. manage the language choice.

No option logic lives here: every section renders and reads itself.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import fileops, i18n


# --- file management (atomic commit / rollback) ------------------------------

class ConfigManager:
    """Manage one gamemode.ini: atomic commit, backup and rollback.

    Writing to ``/etc`` is delegated to the root helper via pkexec/sudo; a
    writable path (tests, user configs) is handled in-process. Either way the
    commit is atomic and has a rollback, via :mod:`fileops`.
    """

    def __init__(self, config_path: str, orig_seed: str = "") -> None:
        self.config_path = config_path
        self.backup_path = config_path + ".bak"
        self.orig_path = config_path + ".orig"
        self.tmp_path = config_path + ".tmp"
        self.orig_seed = orig_seed

    def read_existing(self) -> str:
        """Text of the active file, or an empty string if it is missing."""
        try:
            if os.path.isfile(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    return handle.read()
        except OSError:
            pass
        return ""

    def save(self, content: str) -> None:
        """Commit ``content`` to the managed file (privileged or local)."""
        if is_privileged_path(self.config_path):
            seed_file = self._write_seed_tmp()
            extra_args = [seed_file] if seed_file else []
            try:
                result = run_privileged("commit", self.config_path,
                                                 content=content,
                                                 extra_args=extra_args)
            finally:
                if seed_file:
                    try:
                        os.remove(seed_file)
                    except OSError:
                        pass
            if not result.success:
                detail = (result.stderr or result.stdout or "unknown error").strip()
                raise OSError(detail)
            return
        fileops.write_commit(self.config_path, content,
                             orig_seed_content=self.orig_seed, create_dirs=True)

    def _write_seed_tmp(self) -> Optional[str]:
        """Write the ``.orig`` seed to a temporary file readable by root."""
        if not self.orig_seed or os.path.isfile(self.orig_path):
            return None
        try:
            fd, path = tempfile.mkstemp(prefix="gamemode-orig-", suffix=".ini")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self.orig_seed)
            os.chmod(path, 0o644)
            return path
        except OSError:
            return None

    def rollback_from_backup(self) -> bool:
        """Restore the previous state (``.bak`` -> active file)."""
        try:
            if is_privileged_path(self.config_path):
                return run_privileged("restore-backup",
                                               self.config_path).success
            fileops.restore_from_backup(self.config_path)
            return True
        except OSError:
            return False

    def restore_from_orig(self) -> bool:
        """Restore the pristine state (``.orig`` -> active file)."""
        try:
            if is_privileged_path(self.config_path):
                return run_privileged("restore-orig",
                                               self.config_path).success
            fileops.restore_from_orig(self.config_path)
            return True
        except OSError:
            return False

    def ensure_orig_on_first_run(self, default_content: str) -> None:
        """Create the ``.orig`` baseline once, if it is still missing."""
        if os.path.isfile(self.orig_path):
            return
        seed_content = self.read_existing() or self.orig_seed or default_content
        if is_privileged_path(self.config_path):
            try:
                run_privileged("ensure-orig", self.config_path,
                                        content=seed_content)
            except Exception:
                pass
        else:
            try:
                directory = os.path.dirname(self.config_path) or "."
                os.makedirs(directory, mode=0o700, exist_ok=True)
                fileops.ensure_orig(self.config_path, seed_content=seed_content)
            except Exception:
                pass


# --- configuration locations ------------------------------------------------

def resolve_config_path() -> str:
    """Path of the gamemode.ini managed by the GUI (``/etc`` or ``GAMEMODE_CONFIG``)."""
    override = os.environ.get("GAMEMODE_CONFIG")
    if override:
        return override
    return "/etc/gamemode.ini"


def resolve_base_path() -> Optional[str]:
    """Find the package-installed gamemode.ini, or ``None``."""
    if "GAMEMODE_BASE" in os.environ:
        value = os.environ.get("GAMEMODE_BASE", "").strip()
        return value or None
    xdg = os.environ.get("XDG_DATA_DIRS", "").strip()
    data_dirs = [d for d in xdg.split(":") if d] if xdg else []
    data_dirs += ["/usr/local/share", "/usr/share"]
    for data_dir in data_dirs:
        path = os.path.join(data_dir, "gamemode", "gamemode.ini")
        if os.path.isfile(path):
            return path
    return None


# --- JSON session persistence ------------------------------------------------

def session_path(config_path: str) -> str:
    return config_path + ".session.json"


def save_session(config_path: str, values: Dict[str, object]) -> None:
    """Persist the current values to ``<config>.session.json`` (best effort)."""
    categories: Dict[str, Dict[str, object]] = {}
    for flat_key, value in values.items():
        section, _, key = flat_key.partition(".")
        categories.setdefault(section, {})[key] = value
    data = {"version": 1, "categories": categories}
    try:
        with open(session_path(config_path), "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except OSError:
        pass


def load_session(config_path: str) -> Optional[Dict[str, object]]:
    """Load the flat ``section.key -> value`` mapping from the session JSON."""
    try:
        with open(session_path(config_path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    categories = data.get("categories")
    if isinstance(categories, dict):
        flat: Dict[str, object] = {}
        for section, options in categories.items():
            if isinstance(options, dict):
                for key, value in options.items():
                    flat[f"{section}.{key}"] = value
        return flat
    if isinstance(data.get("values"), dict):
        return data["values"]
    return None


# --- application core (orchestrator) -----------------------------------------

class AppCore:
    """Orchestrates the sections and performs the app-wide operations."""

    def __init__(self, config_path: str, base_path: Optional[str],
                 sections: List, orig_seed: str = "") -> None:
        self.config_path = config_path
        self.base_path = base_path
        self.sections = list(sections)
        self.config_manager = ConfigManager(config_path, orig_seed=orig_seed)

    def render(self) -> str:
        """Join the sections' own output into the gamemode.ini content."""
        parts = [section.render() for section in self.sections]
        parts = [part for part in parts if part]
        if not parts:
            return ""
        return "\n".join(parts)

    def collect_values(self) -> Dict[str, object]:
        """Flat ``section.key -> value`` mapping of every section (for the session)."""
        values: Dict[str, object] = {}
        for section in self.sections:
            for spec in section.options:
                values[f"{section.section_id}.{spec.key}"] = getattr(section.state, spec.key)
        return values

    def save(self) -> None:
        """Commit the combined content atomically and persist the session."""
        self.config_manager.save(self.render())
        save_session(self.config_path, self.collect_values())

    def restore_previous(self) -> bool:
        """Restore the previous state (``.bak``); True on success."""
        return self.config_manager.rollback_from_backup()

    def restore_factory(self) -> bool:
        """Restore GameMode's pristine configuration (``.orig``); True on success."""
        return self.config_manager.restore_from_orig()

    def language_menu(self) -> List[Tuple[str, str]]:
        """``(code, name)`` pairs for the language menu."""
        return i18n.available_langs()

    def active_language(self) -> str:
        """Code of the currently active language."""
        return i18n.current_lang()

    def choose_language(self, code: str) -> None:
        """Persist a new language choice (applied on the next start)."""
        i18n.save_lang(code)


# --- privileged front-end (owned here: save/restore may need root) -----------

@dataclass
class CommandResult:
    """Outcome of the privileged helper process."""

    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    command: str = ""


def _find_executable(name: str, *fallbacks: str) -> Optional[str]:
    """Find an executable in PATH, then among the known absolute paths."""
    path = shutil.which(name)
    if path:
        return path
    for candidate in fallbacks:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _privileged_prefixes() -> List[List[str]]:
    """Available privileged prefixes, in order (pkexec, then sudo)."""
    prefixes: List[List[str]] = []
    pkexec = _find_executable("pkexec", "/usr/bin/pkexec", "/usr/sbin/pkexec")
    if pkexec:
        prefixes.append([pkexec])
    sudo = _find_executable("sudo", "/usr/bin/sudo", "/bin/sudo", "/usr/sbin/sudo")
    if sudo:
        prefixes.append([sudo, "-n"])
    return prefixes


def _privileged_helper_argv(command: str, path: str,
                            extra_args: Optional[List[str]] = None) -> List[str]:
    """Command line that runs the root helper (``privileged.py``)."""
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privileged.py")
    return [sys.executable, helper, command, path] + list(extra_args or [])


def run_privileged(command: str, path: str, content: str = "", timeout: int = 60,
                   extra_args: Optional[List[str]] = None) -> CommandResult:
    """Run a privileged operation, trying pkexec then sudo."""
    argv = _privileged_helper_argv(command, path, extra_args)
    for prefix in _privileged_prefixes():
        try:
            process = subprocess.run(prefix + argv, input=content, capture_output=True,
                                     text=True, timeout=timeout, check=False)
            return CommandResult(process.returncode == 0, process.returncode,
                                 process.stdout, process.stderr,
                                 command=" ".join(prefix + argv))
        except FileNotFoundError:
            continue
        except subprocess.SubprocessError:
            continue
    raise FileNotFoundError("no privileged frontend available (pkexec/sudo)")


def is_privileged_path(path: str) -> bool:
    """True if the destination directory is not writable by the user (e.g. /etc)."""
    directory = os.path.dirname(path) or "/"
    return not os.access(directory, os.W_OK)
