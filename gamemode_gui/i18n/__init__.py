"""Internationalisation: gettext catalogs plus the user's language preference."""

from .settings import (
    DEFAULT_LANG, DEFAULT_SUPPORTED_LANGS, DOMAIN, LOCALE_DIR,
    available_langs, describe_lang_errors, detect_system_lang, ensure_settings,
    fallback_lang, has_catalog, lang_label, language_names, load_saved_lang,
    load_settings, normalize_lang_code, reset_supported_langs, resolve_lang,
    save_lang, save_settings, settings_dir, settings_path, supported_lang,
    supported_langs,
)
from .translator import Translator, current_lang, ntr, tr

__all__ = [
    "DEFAULT_LANG", "DEFAULT_SUPPORTED_LANGS", "DOMAIN", "LOCALE_DIR",
    "Translator", "available_langs", "current_lang", "describe_lang_errors",
    "detect_system_lang", "ensure_settings", "fallback_lang", "has_catalog",
    "lang_label", "language_names", "load_saved_lang", "load_settings",
    "normalize_lang_code", "ntr", "reset_supported_langs", "resolve_lang",
    "save_lang", "save_settings", "settings_dir", "settings_path",
    "supported_lang", "supported_langs", "tr",
]
