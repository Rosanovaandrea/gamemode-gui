"""gettext-backed translator with the project's fallback chain."""

from __future__ import annotations

import gettext as _gettext
from typing import Optional

from .settings import DOMAIN, LOCALE_DIR, DEFAULT_LANG, fallback_lang, resolve_lang


class Translator:
    """Translation table for one language (active -> fallback -> default)."""

    def __init__(self, lang: Optional[str] = None) -> None:
        self.lang = lang or resolve_lang()
        self._catalog = self._load()

    def _load(self) -> _gettext.NullTranslations:
        for code in (self.lang, fallback_lang(), DEFAULT_LANG):
            try:
                return _gettext.translation(DOMAIN, LOCALE_DIR, languages=[code])
            except (FileNotFoundError, OSError):
                continue
        return _gettext.NullTranslations()

    def tr(self, key: str) -> str:
        """Translate a key; a missing key is returned unchanged."""
        return self._catalog.gettext(key)

    def ntr(self, singular: str, plural: str, count: int) -> str:
        """Translate a plural form."""
        return self._catalog.ngettext(singular, plural, count)


_translator = Translator()


def tr(key: str) -> str:
    """Translate a key into the active language."""
    return _translator.tr(key)


def ntr(singular: str, plural: str, count: int) -> str:
    """Translate a plural form into the active language."""
    return _translator.ntr(singular, plural, count)


def current_lang() -> str:
    """Code of the language currently loaded."""
    return _translator.lang
