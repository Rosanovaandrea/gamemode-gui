"""General core: orchestrates sections and runs app-wide file operations."""

from __future__ import annotations

import os
import tempfile
from typing import Dict, List, Optional, Tuple

from gamemode_gui import i18n
from gamemode_gui.config import (
    fileops, load_session, resolve_base_path, resolve_config_path, save_session,
)
from gamemode_gui.services import (
    CommandResult, is_privileged_path, run_privileged,
)


class ConfigManager:
    """Manage one gamemode.ini: atomic commit, backup and rollback."""

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
                                        content=content, extra_args=extra_args)
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
                return run_privileged("restore-backup", self.config_path).success
            fileops.restore_from_backup(self.config_path)
            return True
        except OSError:
            return False

    def restore_from_orig(self) -> bool:
        """Restore the pristine state (``.orig`` -> active file)."""
        try:
            if is_privileged_path(self.config_path):
                return run_privileged("restore-orig", self.config_path).success
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
                run_privileged("ensure-orig", self.config_path, content=seed_content)
            except Exception:
                pass
        else:
            try:
                directory = os.path.dirname(self.config_path) or "."
                os.makedirs(directory, mode=0o700, exist_ok=True)
                fileops.ensure_orig(self.config_path, seed_content=seed_content)
            except Exception:
                pass


class AppCore:
    """Orchestrates the sections and performs the app-wide operations."""

    def __init__(self, config_path: str, base_path: Optional[str],
                 sections: List, orig_seed: str = "", store=None) -> None:
        self.config_path = config_path
        self.base_path = base_path
        self.sections = list(sections)
        self.store = store
        self.config_manager = ConfigManager(config_path, orig_seed=orig_seed)

    def render(self) -> str:
        """Join the sections' own output into the gamemode.ini content."""
        parts = [section.render_ini_section() for section in self.sections]
        return "\n".join(part for part in parts if part)

    def collect_values(self) -> Dict[str, object]:
        """Flat ``section.key -> value`` mapping of every section."""
        return {
            f"{section.section_id}.{spec.key}": getattr(section.state, spec.key)
            for section in self.sections for spec in section.options
        }

    def save(self) -> None:
        """Commit the combined content atomically and persist the session."""
        self.config_manager.save(self.render())
        save_session(self.config_path, self.collect_values())
        if self.store is not None:
            self.store.set_dirty(False)

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
