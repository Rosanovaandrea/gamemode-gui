"""General core: orchestrates sections through the configuration file."""

from __future__ import annotations

from typing import List, Tuple

from configuration import Configuration
from i18n import available_langs, current_lang, save_lang


class AppCore:
    """Orchestrates the sections and performs the app-wide operations."""

    def __init__(self, configuration: Configuration, sections: List,
                 store=None) -> None:
        self.configuration = configuration
        self.config_path = configuration.config_path
        self.base_path = configuration.base_path
        self.sections = list(sections)
        self.store = store

    def render(self) -> str:
        """Return the content that will be written to gamemode.ini."""
        return self.configuration.render(self.sections)

    def save(self) -> None:
        """Write the sections to disk and persist the session."""
        self.configuration.save(self.sections)
        if self.store is not None:
            self.store.set_dirty(False)

    def restore_previous(self) -> bool:
        """Restore the previous state (``.bak``); True on success."""
        return self.configuration.restore_previous()

    def restore_factory(self) -> bool:
        """Restore GameMode's pristine configuration (``.orig``); True on success."""
        return self.configuration.restore_original()

    def language_menu(self) -> List[Tuple[str, str]]:
        """``(code, name)`` pairs for the language menu."""
        return available_langs()

    def active_language(self) -> str:
        """Code of the currently active language."""
        return current_lang()

    def choose_language(self, code: str) -> None:
        """Persist a new language choice (applied on the next start)."""
        save_lang(code)
