"""Internationalisation (i18n) and the user's language preference.

Two responsibilities live here, both purely about language:

  1. the translation table (:class:`Translator`) loaded from ``data/locale``;
  2. the user preference persisted in ``settings.json`` (the set of supported
     languages and the chosen one).

The rest of the application only ever calls :func:`tr`; no visible string is
hardcoded elsewhere. The set of supported languages comes from the settings file
(default ``it``, ``en``) and every entry is validated against the XML files: a
code without a translation file is dropped and reported, without blocking the
app. The active language is chosen, in order, from the saved choice, the system
locale (``LC_ALL`` > ``LC_MESSAGES`` > ``LANG``) and finally English.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

# The locale files are the data this module owns (the shared language concern),
# so the path is computed here rather than in a shared paths module.
_LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "locale")

try:
    import xml.etree.ElementTree as _ET
except Exception:  # pragma: no cover - ElementTree is part of the stdlib
    _ET = None

_DEFAULT_SUPPORTED_LANGS = ("it", "en")
_DEFAULT_LANG = "en"

# Cache of the validated language list plus the configuration errors. Errors are
# (kind, detail) pairs turned into messages by ``describe_lang_errors``; they are
# not translated here because this runs before the translator exists.
_supported_cache: Optional[tuple] = None
_language_errors: List[tuple] = []

# True when the last read of settings.json failed (broken file or not an object).
_settings_load_failed = False


def normalize_lang_code(raw_code: object) -> Optional[str]:
    """Reduce a language code to its short lowercase form (``it``, ``en``, ...).

    Accepts ``it``, ``it_IT``, ``it_IT.UTF-8``, ``en-US`` and the like. It does
    NOT check whether the language is supported: :func:`supported_lang` does.
    """
    if not raw_code:
        return None
    code = str(raw_code).strip().lower()
    for separator in (".", "@"):
        code = code.split(separator, 1)[0]
    code = code.replace("-", "_").split("_", 1)[0]
    return code or None


def _compute_supported_languages() -> None:
    """Validate the configured languages once and record the config errors.

    Error kinds: ``bad_config`` (settings.json broken), ``bad_list``
    (``supported_langs`` is not a list), ``bad_entry`` (a non-code entry),
    ``missing_file`` (language without ``locale/<code>.xml``) and ``empty``
    (nothing usable, fall back to the defaults).
    """
    global _supported_cache, _language_errors
    errors: List[tuple] = []

    raw_languages = load_settings().get("supported_langs")
    if _settings_load_failed:
        errors.append(("bad_config", ""))

    configured: Optional[List[str]] = None
    if raw_languages is None:
        configured = None
    elif isinstance(raw_languages, list):
        configured = []
        for item in raw_languages:
            if not isinstance(item, str):
                errors.append(("bad_entry", str(item)))
                continue
            code = normalize_lang_code(item)
            if code is None:
                errors.append(("bad_entry", str(item)))
            elif code not in configured:
                configured.append(code)
    else:
        errors.append(("bad_list", ""))

    candidates = configured if configured else list(_DEFAULT_SUPPORTED_LANGS)

    valid: List[str] = []
    for code in candidates:
        if os.path.isfile(os.path.join(_LOCALE_DIR, f"{code}.xml")):
            if code not in valid:
                valid.append(code)
        else:
            errors.append(("missing_file", code))

    # If no configured language is usable, fall back to the safe defaults.
    if not valid:
        for code in _DEFAULT_SUPPORTED_LANGS:
            if os.path.isfile(os.path.join(_LOCALE_DIR, f"{code}.xml")) and code not in valid:
                valid.append(code)
        if not valid:
            errors.append(("empty", ""))

    _supported_cache = tuple(valid) if valid else (_DEFAULT_LANG,)
    _language_errors = errors


def supported_langs() -> tuple:
    """Supported language codes, read from the config and validated on disk."""
    if _supported_cache is None:
        _compute_supported_languages()
    return _supported_cache


def reset_supported_langs() -> None:
    """Invalidate the cached language list (called when the config changes)."""
    global _supported_cache
    _supported_cache = None


def lang_label(code: str) -> str:
    """Human name of a language (its XML ``name``), or the upper-case code."""
    path = os.path.join(_LOCALE_DIR, f"{code}.xml")
    if _ET is not None and os.path.isfile(path):
        try:
            name = (_ET.parse(path).getroot().get("name") or "").strip()
            if name:
                return name
        except Exception:
            pass
    return code.upper()


def available_langs() -> List[tuple]:
    """``(code, name)`` pairs for the language menu, in the configured order."""
    return [(code, lang_label(code)) for code in supported_langs()]


def fallback_lang() -> str:
    """Fallback language: English if available, otherwise the first valid one."""
    languages = supported_langs()
    if _DEFAULT_LANG in languages:
        return _DEFAULT_LANG
    return languages[0] if languages else _DEFAULT_LANG


def supported_lang(raw_code: object) -> Optional[str]:
    """Normalised code if it is a supported language, otherwise ``None``."""
    code = normalize_lang_code(raw_code)
    return code if code and code in supported_langs() else None


def detect_system_lang() -> str:
    """Active language from the system locale, with a safe fallback.

    Follows the standard environment precedence (LC_ALL > LC_MESSAGES > LANG):
    the first variable set wins; if it is not a supported language the fallback
    (English) is used.
    """
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw_value = os.environ.get(variable, "").strip()
        if raw_value:
            return supported_lang(raw_value) or fallback_lang()
    return fallback_lang()


# --- user preference (application settings) --------------------------------

def settings_dir() -> str:
    """User settings folder, respecting ``XDG_CONFIG_HOME``."""
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "gamemode-gui")


def settings_path() -> str:
    return os.path.join(settings_dir(), "settings.json")


def load_settings() -> Dict[str, object]:
    """Read ``settings.json``; if missing or unreadable return ``{}``.

    On an unreadable file or a non-object JSON it flags the error (used to warn
    the user) and continues with the defaults.
    """
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
    """Write ``settings.json`` (best effort, never fatal)."""
    try:
        os.makedirs(settings_dir(), mode=0o700, exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
    except OSError:
        pass


def ensure_settings() -> None:
    """Make sure settings.json exists and lists ``supported_langs``."""
    settings = load_settings()
    if "supported_langs" not in settings:
        settings["supported_langs"] = list(_DEFAULT_SUPPORTED_LANGS)
        save_settings(settings)


def load_saved_lang() -> Optional[str]:
    """Language chosen by the user, if present and supported, otherwise None."""
    return supported_lang(load_settings().get("lang"))


def save_lang(lang: str) -> None:
    """Persist the user's language choice (it takes precedence over all)."""
    code = supported_lang(lang) or fallback_lang()
    settings = load_settings()
    settings.setdefault("supported_langs", list(_DEFAULT_SUPPORTED_LANGS))
    settings["lang"] = code
    save_settings(settings)


def resolve_lang() -> str:
    """Effective language: saved choice > system locale > fallback."""
    return load_saved_lang() or detect_system_lang() or fallback_lang()


class Translator:
    """Translation table loaded from an XML language file.

    A missing key returns the key itself: the fallback is visible, never a
    crash. Loading is chained: active language -> fallback -> default.
    """

    def __init__(self, lang: Optional[str] = None) -> None:
        self.lang = lang or resolve_lang()
        self._strings: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if _ET is None:
            return
        for code in (self.lang, fallback_lang(), _DEFAULT_LANG):
            path = os.path.join(_LOCALE_DIR, f"{code}.xml")
            if os.path.isfile(path):
                break
        else:
            return
        try:
            root = _ET.parse(path).getroot()
        except Exception:
            return
        for entry in root.findall("entry"):
            key = entry.get("id")
            if key is not None and entry.text:
                # XML files use the "\n" sequence for line breaks.
                self._strings[key] = entry.text.strip().replace("\\n", "\n")

    def tr(self, key: str) -> str:
        return self._strings.get(key, key)


_translator = Translator()


def tr(key: str) -> str:
    """Translate a key into the current language."""
    return _translator.tr(key)


def current_lang() -> str:
    """Code of the language currently active in the translator."""
    return _translator.lang


def describe_lang_errors() -> List[str]:
    """Localised messages about the language configuration errors.

    Call it once the UI is ready (it uses :func:`tr`); the raw errors are
    computed when the language list is first read.
    """
    supported_langs()  # make sure the errors have been computed
    messages: List[str] = []
    for kind, detail in _language_errors:
        if kind == "missing_file":
            messages.append(tr("msg.lang.missing_file").format(lang=detail))
        elif kind == "bad_entry":
            messages.append(tr("msg.lang.bad_entry").format(value=detail))
        elif kind == "bad_list":
            messages.append(tr("msg.lang.bad_list"))
        elif kind == "bad_config":
            messages.append(tr("msg.lang.bad_config"))
        elif kind == "empty":
            messages.append(tr("msg.lang.empty"))
    return messages
