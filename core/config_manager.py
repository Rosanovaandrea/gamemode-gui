"""Atomic, crash-safe write of ``gamemode.ini``.

Strategy (from the specification):

1. Render the full configuration to a temporary file ``gamemode.ini.tmp``.
2. ``fsync`` the temporary file.
3. If ``gamemode.ini`` exists, copy it to ``gamemode.ini.bak``.
4. ``os.replace(tmp, gamemode.ini)`` -- atomic on POSIX.
5. On failure at step 4, restore ``.bak`` over ``gamemode.ini``.
6. Remove the temporary file if it still exists.

File permissions are pinned to ``0o644`` and the config directory is kept
at ``0o700`.
"""

from __future__ import annotations

import os
import shutil
import tempfile


class ConfigManager:
    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self.backup_path = config_path + ".bak"
        self.orig_path = config_path + ".orig"
        self.tmp_path = config_path + ".tmp"

    # -- paths -------------------------------------------------------------
    def directory(self) -> str:
        return os.path.dirname(self.config_path)

    def ensure_directory(self) -> None:
        """Create the config directory with ``0o700`` if missing."""
        d = self.directory()
        if d and not os.path.isdir(d):
            os.makedirs(d, mode=0o700, exist_ok=True)

    # -- atomic write ------------------------------------------------------
    def _write_tmp(self, content: str) -> None:
        with open(self.tmp_path, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())

    def save(self, content: str) -> None:
        """Commit ``content`` using the backup + atomic replace strategy.

        Raises :class:`OSError` on failure, after attempting an automatic
        rollback.
        """
        self.ensure_directory()

        # 1. Write temporary file
        self._write_tmp(content)
        # pin permissions on the temp too
        os.chmod(self.tmp_path, 0o644)

        # 2. Make a backup of the current config if present
        had_previous = os.path.isfile(self.config_path)
        if had_previous:
            shutil.copy2(self.config_path, self.backup_path)

        # 3. Atomic replace
        try:
            os.replace(self.tmp_path, self.config_path)
        except OSError:
            # 4. Rollback
            self._rollback(had_previous)
            raise

        os.chmod(self.config_path, 0o644)

        # 5. Cleanup left-over tmp
        self._cleanup_tmp()

    def _rollback(self, had_previous: bool) -> None:
        try:
            if had_previous and os.path.isfile(self.backup_path):
                shutil.copy2(self.backup_path, self.config_path)
        except OSError:
            pass

    def _cleanup_tmp(self) -> None:
        if os.path.exists(self.tmp_path):
            try:
                os.remove(self.tmp_path)
            except OSError:
                pass

    # -- backup recovery ----------------------------------------------------
    def rollback_from_backup(self) -> bool:
        """Manually restore ``.bak`` over the active config."""
        if not os.path.isfile(self.backup_path):
            return False
        shutil.copy2(self.backup_path, self.config_path)
        os.chmod(self.config_path, 0o644)
        return True

    def restore_from_orig(self) -> bool:
        """Manually restore ``.orig`` (the pristine first-run copy)."""
        if not os.path.isfile(self.orig_path):
            return False
        shutil.copy2(self.orig_path, self.config_path)
        os.chmod(self.config_path, 0o644)
        return True