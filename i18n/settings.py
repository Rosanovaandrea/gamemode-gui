"""Language preference and supported-language discovery."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

DOMAIN = "gamemode-gui"
LOCALE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "locale")
LANGUAGES_FILE = os.path.join(LOCALE_DIR, "languages.json")
DEFAULT_SUPPORTED_LANGS = ("it", "en")
DEFAULT_LANG = "en"

_supported_cache: Optional[tuple] = None
_language_errors: List[tuple] = []
_settings_load_failed = False


def normalize_lang_code(raw_code: object) -> Optional[str]:
    """Reduce a locale code to its short lowercase form (``it_IT.UTF-8`` -> ``it``)."""
    if not raw_code:
        return None
    code = str(raw_code).strip().lower()
    for separator in (".", "@"):
        code = code.split(separator, 1)[0]
    code = code.replace("-", "_").split("_", 1)[0]
    return code or None


def language_names() -> Dict[str, str]:
    """Human-readable names of the available languages."""
    try:
        with open(LANGUAGES_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError):
        return {}


def has_catalog(code: str) -> bool:
    """True if the compiled gettext catalog for ``code`` exists."""
    return os.path.isfile(os.path.join(LOCALE_DIR, code, "LC_MESSAGES",
                                       f"{DOMAIN}.mo"))


def _compute_supported_languages() -> None:
    global _supported_cache, _language_errors
    errors: List[tuple] = []
    raw_languages = load_settings().get("supported_langs")
    if _settings_load_failed:
        errors.append(("bad_config", ""))

    configured: Optional[List[str]] = None
    match raw_languages:
        case None:
            configured = None
        case list() as items:
            configured = []
            for item in items:
                code = normalize_lang_code(item) if isinstance(item, str) else None
                if code is None:
                    errors.append(("bad_entry", str(item)))
                elif code not in configured:
                    configured.append(code)
        case _:
            errors.append(("bad_list", ""))

    valid: List[str] = []
    for code in configured or list(DEFAULT_SUPPORTED_LANGS):
        if has_catalog(code):
            valid.append(code)
        else:
            errors.append(("missing_file", code))

    if not valid:
        valid = [code for code in DEFAULT_SUPPORTED_LANGS if has_catalog(code)]
        if not valid:
            errors.append(("empty", ""))
    _supported_cache = tuple(valid) or (DEFAULT_LANG,)
    _language_errors = errors


def supported_langs() -> tuple:
    """Supported language codes, validated against the compiled catalogs."""
    if _supported_cache is None:
        _compute_supported_languages()
    return _supported_cache


def reset_supported_langs() -> None:
    """Invalidate the cached language list."""
    global _supported_cache
    _supported_cache = None


def lang_label(code: str) -> str:
    """Human name of a language, or its upper-case code."""
    return language_names().get(code, code.upper())


def available_langs() -> List[tuple]:
    """``(code, name)`` pairs for the language menu."""
    return [(code, lang_label(code)) for code in supported_langs()]


def fallback_lang() -> str:
    """English when available, otherwise the first supported language."""
    languages = supported_langs()
    return DEFAULT_LANG if DEFAULT_LANG in languages else (languages[0] if languages else DEFAULT_LANG)


def supported_lang(raw_code: object) -> Optional[str]:
    """Normalised code when supported, otherwise ``None``."""
    code = normalize_lang_code(raw_code)
    return code if code and code in supported_langs() else None


def detect_system_lang() -> str:
    """Language from the system locale (``LC_ALL`` > ``LC_MESSAGES`` > ``LANG``)."""
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw_value = os.environ.get(variable, "").strip()
        if raw_value:
            return supported_lang(raw_value) or fallback_lang()
    return fallback_lang()


def settings_dir() -> str:
    """User settings folder, respecting ``XDG_CONFIG_HOME``."""
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "gamemode-gui")


def settings_path() -> str:
    return os.path.join(settings_dir(), "settings.json")


def load_settings() -> Dict[str, object]:
    """Read ``settings.json``; an unreadable or non-object file yields ``{}``."""
    global _settings_load_failed
    _settings_load_failed = False
    try:
        with open(settings_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        _settings_load_failed = True
        return {}
    if not isinstance(data, dict):
        _settings_load_failed = True
        return {}
    return data


def save_settings(settings: Dict[str, object]) -> None:
    """Write ``settings.json`` (best effort)."""
    try:
        os.makedirs(settings_dir(), mode=0o700, exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
    except OSError:
        pass


def ensure_settings() -> None:
    """Create settings.json with the default language list when missing."""
    settings = load_settings()
    if "supported_langs" not in settings:
        settings["supported_langs"] = list(DEFAULT_SUPPORTED_LANGS)
        save_settings(settings)


def load_saved_lang() -> Optional[str]:
    """The saved language when present and supported."""
    return supported_lang(load_settings().get("lang"))


def save_lang(lang: str) -> None:
    """Persist the language choice; it takes precedence over the system locale."""
    code = supported_lang(lang) or fallback_lang()
    settings = load_settings()
    settings.setdefault("supported_langs", list(DEFAULT_SUPPORTED_LANGS))
    settings["lang"] = code
    save_settings(settings)


def resolve_lang() -> str:
    """Effective language: saved choice > system locale > fallback."""
    return load_saved_lang() or detect_system_lang() or fallback_lang()


def describe_lang_errors() -> List[str]:
    """Localised messages for the language-configuration errors."""
    from .translator import tr

    supported_langs()
    messages: List[str] = []
    for kind, detail in _language_errors:
        match kind:
            case "missing_file":
                messages.append(tr("msg.lang.missing_file").format(lang=detail))
            case "bad_entry":
                messages.append(tr("msg.lang.bad_entry").format(value=detail))
            case "bad_list":
                messages.append(tr("msg.lang.bad_list"))
            case "bad_config":
                messages.append(tr("msg.lang.bad_config"))
            case "empty":
                messages.append(tr("msg.lang.empty"))
    return messages
