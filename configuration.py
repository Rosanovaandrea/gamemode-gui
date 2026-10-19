"""Read and write the gamemode.ini file, atomically and with backups.

This is the single place that knows how the file is loaded into the sections and
how the sections are rendered back into the file. Writes use copy-on-write:
the new content goes to a temporary file, the current file is copied to ``.bak``
and ``.orig``, then ``os.replace`` swaps the new file into place.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, List, Optional

from services.privileged import (
    COMMAND_COMMIT, COMMAND_ENSURE_ORIG, COMMAND_RESTORE_BACKUP,
    COMMAND_RESTORE_ORIG, is_privileged_path, run_privileged,
)

_FILE_MODE = 0o644


# --- paths ------------------------------------------------------------------

def resolve_config_path() -> str:
    """Path managed by the GUI (``GAMEMODE_CONFIG`` or ``/etc/gamemode.ini``)."""
    return os.environ.get("GAMEMODE_CONFIG") or "/etc/gamemode.ini"


def resolve_base_path() -> Optional[str]:
    """Find the package-installed gamemode.ini, or ``None``."""
    if "GAMEMODE_BASE" in os.environ:
        return os.environ.get("GAMEMODE_BASE", "").strip() or None
    xdg = os.environ.get("XDG_DATA_DIRS", "").strip()
    data_dirs = [d for d in xdg.split(":") if d] if xdg else []
    data_dirs += ["/usr/local/share", "/usr/share"]
    for data_dir in data_dirs:
        path = os.path.join(data_dir, "gamemode", "gamemode.ini")
        if os.path.isfile(path):
            return path
    return None


# --- INI slices -------------------------------------------------------------

def extract_section(text: str, section_id: str) -> Dict[str, List[str]]:
    """Return ``key -> [raw values]`` for ``[section_id]`` from INI text."""
    result: Dict[str, List[str]] = {}
    section = None
    current_key = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match line:
            case _ if not line or line.startswith((";", "#")):
                continue
            case _ if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()
                current_key = None
            case _ if section == section_id and ("=" in line or ":" in line):
                separator = "=" if "=" in line else ":"
                name, _, value = line.partition(separator)
                current_key = name.strip()
                result.setdefault(current_key, []).append(strip_comment(value.strip()))
            case _ if section == section_id and current_key is not None:
                result.setdefault(current_key, []).append(strip_comment(line))
    return result


def strip_comment(value: str) -> str:
    """Remove a trailing ``;``/``#`` comment from a value."""
    for index, char in enumerate(value):
        if char in (";", "#") and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value


def read_text(path: Optional[str]) -> str:
    """Read a text file; missing or unreadable files yield ``""``."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


# --- session sidecar --------------------------------------------------------

def session_path(config_path: str) -> str:
    return config_path + ".session.json"


def save_session(config_path: str, values: Dict[str, object]) -> None:
    """Persist the last values next to the config (best effort)."""
    categories: Dict[str, Dict[str, object]] = {}
    for flat_key, value in values.items():
        section, _, key = flat_key.partition(".")
        categories.setdefault(section, {})[key] = value
    try:
        with open(session_path(config_path), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "categories": categories}, handle, indent=2)
    except OSError:
        pass


def load_session(config_path: str) -> Optional[Dict[str, object]]:
    """Load the flat ``section.key -> value`` mapping from the session JSON."""
    try:
        with open(session_path(config_path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    match data:
        case dict() if isinstance(data.get("categories"), dict):
            return {
                f"{section}.{key}": value
                for section, options in data["categories"].items()
                if isinstance(options, dict)
                for key, value in options.items()
            }
        case dict() if isinstance(data.get("values"), dict):
            return data["values"]
        case _:
            return None


# --- atomic copy-on-write ---------------------------------------------------

def _fsync_dir(directory: str) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write(path: str, data: bytes) -> None:
    """Write ``data`` to a temp file in the same directory, then replace ``path``."""
    directory = os.path.dirname(path) or "."
    descriptor, temporary = tempfile.mkstemp(
        prefix=".gamemode-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, _FILE_MODE)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    _fsync_dir(directory)


def _atomic_copy(source: str, target: str) -> None:
    with open(source, "rb") as handle:
        _atomic_write(target, handle.read())


def ensure_orig(target: str, seed_content: Optional[str] = None,
                fallback_path: Optional[str] = None) -> None:
    """Create ``<target>.orig`` once, using the current file or a fallback."""
    original = target + ".orig"
    if os.path.exists(original):
        return
    if os.path.isfile(target):
        _atomic_copy(target, original)
    elif seed_content is not None:
        _atomic_write(original, seed_content.encode("utf-8"))
    elif fallback_path and os.path.isfile(fallback_path):
        _atomic_copy(fallback_path, original)


def write_commit(target: str, content: str, orig_seed_content: Optional[str] = None,
                 create_dirs: bool = False) -> None:
    """Atomically write ``content`` to ``target`` with ``.orig`` and ``.bak``."""
    directory = os.path.dirname(target) or "."
    if create_dirs:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    temporary = target + ".tmp"
    _atomic_write(temporary, content.encode("utf-8"))
    try:
        ensure_orig(target, seed_content=orig_seed_content, fallback_path=temporary)
        if os.path.isfile(target):
            _atomic_copy(target, target + ".bak")
        os.replace(temporary, target)
        os.chmod(target, _FILE_MODE)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass
    _fsync_dir(directory)


def restore_from_backup(target: str) -> None:
    """Restore ``<target>.bak`` -> ``target`` atomically."""
    backup = target + ".bak"
    if not os.path.isfile(backup):
        raise FileNotFoundError("no backup available")
    _atomic_copy(backup, target)


def restore_from_orig(target: str) -> None:
    """Restore ``<target>.orig`` -> ``target`` atomically."""
    original = target + ".orig"
    if not os.path.isfile(original):
        raise FileNotFoundError("no original available")
    _atomic_copy(original, target)


# --- configuration ----------------------------------------------------------

class Configuration:
    """Load a gamemode.ini into sections and save the sections back to it."""

    def __init__(self, config_path: str, base_path: Optional[str] = None,
                 orig_seed: str = "") -> None:
        self.config_path = config_path
        self.base_path = base_path
        self.orig_seed = orig_seed

    def load(self, sections: List) -> None:
        """Read the base/override files and load every section from them."""
        base_text = read_text(self.base_path)
        override_text = read_text(self.config_path)
        session = None
        if not os.path.isfile(self.config_path) and self.base_path is None:
            session = load_session(self.config_path)
        for section in sections:
            section.load_texts(base_text, override_text, session)

    def render(self, sections: List) -> str:
        """Join the sections' rendered blocks into the file content."""
        return "\n".join(
            rendered for section in sections
            if (rendered := section.render_ini_section())
        )

    def save(self, sections: List) -> None:
        """Write the sections to the managed file and persist the session."""
        content = self.render(sections)
        if is_privileged_path(self.config_path):
            self.ensure_orig()
            result = run_privileged(COMMAND_COMMIT, self.config_path, content=content)
            if not result.success:
                raise OSError((result.stderr or result.stdout or "unknown error").strip())
        else:
            write_commit(self.config_path, content,
                         orig_seed_content=self.orig_seed, create_dirs=True)
        save_session(self.config_path, {
            f"{section.section_id}.{option_spec.key}":
                getattr(section.state, option_spec.key)
            for section in sections for option_spec in section.options
        })

    def ensure_orig(self) -> None:
        """Create the pristine baseline on first run."""
        if os.path.isfile(self.config_path + ".orig"):
            return
        if is_privileged_path(self.config_path):
            try:
                run_privileged(COMMAND_ENSURE_ORIG, self.config_path,
                               content=self.orig_seed)
            except Exception:
                pass
        else:
            try:
                os.makedirs(os.path.dirname(self.config_path) or ".",
                            mode=0o700, exist_ok=True)
                ensure_orig(self.config_path, seed_content=self.orig_seed)
            except Exception:
                pass

    def restore_previous(self) -> bool:
        """Restore ``.bak`` -> active file."""
        try:
            if is_privileged_path(self.config_path):
                return run_privileged(COMMAND_RESTORE_BACKUP, self.config_path).success
            restore_from_backup(self.config_path)
            return True
        except OSError:
            return False

    def restore_original(self) -> bool:
        """Restore ``.orig`` -> active file."""
        try:
            if is_privileged_path(self.config_path):
                return run_privileged(COMMAND_RESTORE_ORIG, self.config_path).success
            restore_from_orig(self.config_path)
            return True
        except OSError:
            return False
