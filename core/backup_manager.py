"""Backup / orig management.

* ``gamemode.ini.orig`` is the pristine first-run copy. It is created only
  once and never modified automatically; the user can restore it.
* ``gamemode.ini.bak`` is the previous configuration, refreshed at every save.
"""

from __future__ import annotations

import os

from .config_manager import ConfigManager
from .renderer import default_ini


class BackupManager:
    def __init__(self, cm: ConfigManager) -> None:
        self.cm = cm

    @property
    def has_orig(self) -> bool:
        return os.path.isfile(self.cm.orig_path)

    @property
    def has_backup(self) -> bool:
        return os.path.isfile(self.cm.backup_path)

    def ensure_orig(self, content: str) -> None:
        """Create ``.orig`` on first run if it does not yet exist."""
        self.cm.ensure_directory()
        if not self.has_orig:
            with open(self.cm.orig_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.chmod(self.cm.orig_path, 0o644)

    def ensure_orig_from_existing_or_default(self, existing_content: str) -> None:
        """Seed ``.orig`` from the existing config, or from table defaults."""
        content = existing_content if existing_content != "" else default_ini()
        self.ensure_orig(content)