"""Unified core logic of the GameMode GUI.

This module collects ALL the non-GUI logic of the application:

  * loading the option definitions from `options.json`
    (single source of truth: one JSON entry per option)
  * resolving the "special" values read from the system (e.g. CPU governor)
  * INI renderer (definitions + values -> gamemode.ini text)
  * INI reading (keeps repeated lists)
  * configuration file management (atomic write, backup, rollback),
    both on the user path and in /etc (via privileged helper)
  * daemon utilities (test, restart, gamemode group)
  * internationalisation via external XML files (locale/<lang>.xml)

No GTK dependency in here: the logic is testable without a display.
"""

from __future__ import annotations

import getpass
import glob
import grp
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import fileops

# ===========================================================================
# 1. INTERNATIONALISATION (i18n)
# ===========================================================================
# The language is managed through external files in `locale/<lang>.xml`.
#
# The list of available languages is NOT hardcoded: it is read from the
# `supported_langs` key of the settings file (settings.json), with a fallback to
# the Italian/English defaults. Every entry is validated: a code without a
# `locale/<code>.xml` file is dropped and reported (see
# `describe_lang_errors()`), without blocking the app.
#
# Priority order for the active language:
#   1. the user's saved choice (`lang` in settings.json): takes precedence;
#   2. the system locale (LC_ALL > LC_MESSAGES > LANG);
#   3. English ("en") as the default.
#
# No hardcoded strings in the code: use `tr("key")`.

_LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")
_DEFAULT_SUPPORTED_LANGS = ("it", "en")
_DEFAULT_LANG = "en"

try:
    import xml.etree.ElementTree as _ET
except Exception:  # pragma: no cover
    _ET = None

# Cache of the validated language list + configuration errors. Errors are
# (kind, detail) pairs formattable with `describe_lang_errors()`: `tr()` is not
# used here because it would be called before the translator exists.
_langs_cache: Optional[tuple] = None
_langs_errors: List[tuple] = []


def normalize_lang_code(raw: object) -> Optional[str]:
    """Reduce a language code to its short lowercase form (``it``, ``en``, …).

    Accepts ``it``, ``it_IT``, ``it_IT.UTF-8``, ``en-US`` and the like. It does
    NOT check whether the language is supported: `supported_lang` does that.
    """
    if not raw:
        return None
    code = str(raw).strip().lower()
    for sep in (".", "@"):
        code = code.split(sep, 1)[0]
    code = code.replace("-", "_").split("_", 1)[0]
    return code or None


def lang_file_path(code: str) -> str:
    """Path of the language file ``locale/<code>.xml``."""
    return os.path.join(_LOCALE_DIR, f"{code}.xml")


def _has_lang_file(code: str) -> bool:
    return os.path.isfile(lang_file_path(code))


def _compute_supported_langs() -> None:
    """Compute the valid language list once and record the config errors.

    Possible errors (kind/detail pairs):
      * ``bad_config``   -> settings.json unreadable or not a JSON object;
      * ``bad_list``     -> `supported_langs` is not a list;
      * ``bad_entry``    -> a list entry is not a valid code;
      * ``missing_file`` -> a language without `locale/<code>.xml`;
      * ``empty``        -> no usable language (fallback to English).
    """
    global _langs_cache, _langs_errors
    errors: List[tuple] = []

    raw = load_settings().get("supported_langs")
    if _settings_load_failed:
        errors.append(("bad_config", ""))

    configured: Optional[List[str]] = None
    if raw is None:
        configured = None
    elif isinstance(raw, list):
        configured = []
        for item in raw:
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
        if _has_lang_file(code):
            if code not in valid:
                valid.append(code)
        else:
            errors.append(("missing_file", code))

    # If no configured language is usable, fall back to the safe defaults.
    if not valid:
        for code in _DEFAULT_SUPPORTED_LANGS:
            if _has_lang_file(code) and code not in valid:
                valid.append(code)
        if not valid:
            errors.append(("empty", ""))

    _langs_cache = tuple(valid) if valid else (_DEFAULT_LANG,)
    _langs_errors = errors


def supported_langs() -> tuple:
    """Supported language list: read from the config and validated on the files."""
    if _langs_cache is None:
        _compute_supported_langs()
    return _langs_cache


def reset_supported_langs() -> None:
    """Invalidate the language-list cache (used when the config changes)."""
    global _langs_cache
    _langs_cache = None


def lang_label(code: str) -> str:
    """Language name from the ``name`` attribute of its XML, or the upper-case code."""
    path = lang_file_path(code)
    if _ET is not None and os.path.isfile(path):
        try:
            name = (_ET.parse(path).getroot().get("name") or "").strip()
            if name:
                return name
        except Exception:
            pass
    return code.upper()


def available_langs() -> List[tuple]:
    """``(code, name)`` pairs for the menu, in the configured order."""
    return [(code, lang_label(code)) for code in supported_langs()]


def _fallback_lang() -> str:
    """Fallback language: the default if available, otherwise the first valid one."""
    langs = supported_langs()
    if _DEFAULT_LANG in langs:
        return _DEFAULT_LANG
    return langs[0] if langs else _DEFAULT_LANG


def supported_lang(raw: object) -> Optional[str]:
    """Normalised code, only if it is a supported language; otherwise ``None``."""
    code = normalize_lang_code(raw)
    return code if code and code in supported_langs() else None


def detect_system_lang() -> str:
    """Language from the system locale, with a safe fallback.

    Follows the standard environment-variable precedence
    (LC_ALL > LC_MESSAGES > LANG): the first one set wins; if it is not a
    supported language, the fallback (English) is used.
    """
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw = os.environ.get(var, "").strip()
        if raw:
            return supported_lang(raw) or _fallback_lang()
    return _fallback_lang()


# --- user preference (application settings) --------------------------------
# Separate from the gamemode.ini file: it is an application preference, not a
# daemon option, and must not end up in /etc.

# True if the last read of settings.json failed (broken file or not an object).
_settings_load_failed = False


def settings_dir() -> str:
    """User settings folder (respects XDG_CONFIG_HOME)."""
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "gamemode-gui")


def settings_path() -> str:
    return os.path.join(settings_dir(), "settings.json")


def load_settings() -> Dict[str, object]:
    """Read ``settings.json``; if missing or unreadable returns ``{}``.

    On an unreadable file or a non-object JSON it flags the error (used to warn
    the user) and continues with the defaults.
    """
    global _settings_load_failed
    _settings_load_failed = False
    try:
        with open(settings_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
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
        with open(settings_path(), "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
    except OSError:
        pass


def ensure_settings() -> None:
    """Make sure settings.json exists and contains ``supported_langs``.

    The file is created on first run with the default language list, so it can be
    read/modified directly by the user.
    """
    settings = load_settings()
    if "supported_langs" not in settings:
        settings["supported_langs"] = list(_DEFAULT_SUPPORTED_LANGS)
        save_settings(settings)


def load_saved_lang() -> Optional[str]:
    """Language chosen by the user, if present and supported; otherwise None."""
    return supported_lang(load_settings().get("lang"))


def save_lang(lang: str) -> None:
    """Save the language chosen by the user (it will take precedence over all)."""
    code = supported_lang(lang) or _fallback_lang()
    settings = load_settings()
    settings.setdefault("supported_langs", list(_DEFAULT_SUPPORTED_LANGS))
    settings["lang"] = code
    save_settings(settings)


def resolve_lang() -> str:
    """Effective language: saved choice > system locale > fallback."""
    return load_saved_lang() or detect_system_lang() or _fallback_lang()


class Translator:
    """Load a translation table from an XML file and provide `tr()`.

    If a key is missing, the key itself is returned (visible fallback, never a
    crash).
    """

    def __init__(self, lang: Optional[str] = None) -> None:
        self.lang = lang or resolve_lang()
        self._strings: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if _ET is None:
            return
        # Chained fallback: active language -> fallback language -> default.
        path = lang_file_path(self.lang)
        if not os.path.isfile(path):
            path = lang_file_path(_fallback_lang())
        if not os.path.isfile(path):
            path = lang_file_path(_DEFAULT_LANG)
        if not os.path.isfile(path):
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
    """Translate a key into the current language (default: English)."""
    return _translator.tr(key)


def current_lang() -> str:
    """Code of the language currently active in the translator."""
    return _translator.lang


def describe_lang_errors() -> List[str]:
    """Localised messages about the language configuration errors.

    Call it once the UI is ready (it uses `tr`); the raw errors are in
    ``_langs_errors``, computed when the language list is read.
    """
    supported_langs()  # make sure the errors have been computed
    messages: List[str] = []
    for kind, detail in _langs_errors:
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


# ===========================================================================
# 2. OPTION DEFINITIONS (loaded from options.json)
# ===========================================================================
# Every option is described ONCE, as a JSON entry. The fields:
#
#   key             INI key name
#   description_id  i18n key of the description
#   label_id        (optional) i18n key of the visible name (default: key)
#   value_type      int | float | bool | string | choice | list | cores | enable | toggle_entry
#   widget          stepper | switch | radio | list | cores | entry
#   range           [min, max] for numeric values (null = unbounded)
#   choices         allowed values for value_type "choice"
#   default         default value
#   special         true if the values are read from the system
#   special_source  source of the special values (e.g. "cpu_governors")
#   on_value        for value_type "enable": value written when it is active
#   depends_on      id of another option this one depends on
#   comment         comment emitted in the INI file above the option
#   target/entry    for value_type "toggle_entry": the switch adds/removes the
#                   `entry` string to/from the `target` list (e.g. notification in start)
#
# At category level, `toggle_card_id` is the i18n key of the title of the card
# that collects the "toggle_entry" options at the top of the tab.

_OPTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "options.json")


@dataclass(frozen=True)
class OptionSpec:
    """Description of a single key of an INI section."""

    section: str
    key: str
    type: str
    default: Any
    template: str
    description: str
    description_id: str = ""
    label_id: Optional[str] = None
    widget: str = "entry"
    special: bool = False
    special_source: Optional[str] = None
    choices: Optional[list] = None
    choice_labels: Optional[dict] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    on_value: Optional[str] = None
    depends_on: Optional[str] = None
    comment: str = ""
    target: Optional[str] = None
    entry: Optional[str] = None

    @property
    def id(self) -> str:
        return f"{self.section}.{self.key}"

    @property
    def label(self) -> str:
        return tr(self.label_id) if self.label_id else self.key


@dataclass(frozen=True)
class Category:
    """Category (INI section + tab) with its options."""

    id: str
    tab_id: str
    title_id: str
    subtitle_id: str
    banner_id: Optional[str]
    options: tuple
    toggle_card_id: Optional[str] = None


def _spec_from_json(section: str, raw: dict) -> OptionSpec:
    key = raw["key"]
    rng = raw.get("range") or [None, None]
    return OptionSpec(
        section=section,
        key=key,
        type=raw.get("value_type", "string"),
        default=raw.get("default"),
        template=f"{key}={{value}}",
        description=tr(raw["description_id"]),
        description_id=raw["description_id"],
        label_id=raw.get("label_id"),
        widget=raw.get("widget", "entry"),
        special=bool(raw.get("special", False)),
        special_source=raw.get("special_source"),
        choices=raw.get("choices"),
        choice_labels=raw.get("choice_labels"),
        min_value=rng[0] if rng else None,
        max_value=rng[1] if len(rng) > 1 else None,
        on_value=raw.get("on_value"),
        depends_on=raw.get("depends_on"),
        comment=raw.get("comment", ""),
        target=raw.get("target"),
        entry=raw.get("entry"),
    )


def load_categories(path: str = _OPTIONS_FILE) -> List[Category]:
    """Load the categories and options from ``options.json``."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    categories: List[Category] = []
    for cat in data.get("categories", []):
        section = cat["id"]
        specs = tuple(_spec_from_json(section, raw) for raw in cat.get("options", []))
        categories.append(Category(
            id=section,
            tab_id=cat.get("tab_id", f"tab.{section}"),
            title_id=cat.get("title_id", f"step.{section}.title"),
            subtitle_id=cat.get("subtitle_id", f"step.{section}.subtitle"),
            banner_id=cat.get("banner_id"),
            options=specs,
            toggle_card_id=cat.get("toggle_card_id"),
        ))
    return categories


CATEGORIES: List[Category] = load_categories()
OPTIONS: List[OptionSpec] = [spec for cat in CATEGORIES for spec in cat.options]
SECTIONS_ORDER: List[str] = [cat.id for cat in CATEGORIES]
OPTIONS_BY_ID: Dict[str, OptionSpec] = {spec.id: spec for spec in OPTIONS}

# Options grouped by section, in options.json order (used by the renderer).
OPTIONS_BY_SECTION: Dict[str, List[OptionSpec]] = {section: [] for section in SECTIONS_ORDER}
for _spec in OPTIONS:
    OPTIONS_BY_SECTION.setdefault(_spec.section, []).append(_spec)

# "toggle_entry" options grouped by target list (e.g. custom.start).
TOGGLE_ENTRIES_BY_TARGET: Dict[str, List[OptionSpec]] = {}
for _spec in OPTIONS:
    if _spec.type == "toggle_entry" and _spec.target:
        TOGGLE_ENTRIES_BY_TARGET.setdefault(_spec.target, []).append(_spec)


# ===========================================================================
# 2b. PRESENTATION (data-driven content, like options.json)
# ===========================================================================
# The "Presentation" tab contains no options: it is a text page split into
# blocks. The structure (which blocks, in what order, which are warnings) lives
# in presentation.json, while the actual texts live in the language files
# (data-driven + i18n). Adding a block = JSON entry + i18n keys.

_PRESENTATION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "presentation.json")


@dataclass(frozen=True)
class PresentationBlock:
    """A presentation block: heading + text (+ optional warning)."""

    id: str
    heading_id: str
    body_id: str
    warning: bool = False


@dataclass(frozen=True)
class Presentation:
    """Content of the Presentation tab (title, subtitle, blocks)."""

    title_id: str
    subtitle_id: str
    blocks: tuple


def load_presentation(path: str = _PRESENTATION_FILE) -> Presentation:
    """Load the Presentation blocks from ``presentation.json``."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return Presentation("presentation.title", "presentation.subtitle", ())
    blocks = tuple(
        PresentationBlock(
            id=str(block.get("id", "")),
            heading_id=block.get("heading_id", ""),
            body_id=block.get("body_id", ""),
            warning=bool(block.get("warning", False)),
        )
        for block in data.get("blocks", [])
    )
    return Presentation(
        title_id=data.get("title_id", "presentation.title"),
        subtitle_id=data.get("subtitle_id", "presentation.subtitle"),
        blocks=blocks,
    )


PRESENTATION: Presentation = load_presentation()


# ===========================================================================
# 3. CONFIGURATION PATHS (daemon load order)
# ===========================================================================
# GameMode loads and merges in this order:
#   1. <datadir>/gamemode/gamemode.ini   (package-installed file, "base")
#   2. /etc/gamemode.ini                 (administrator override)
#   3. ~/.config/gamemode.ini            (user)
#   4. $PWD/gamemode.ini                 (local)
# The GUI uses the installed file as "base" and writes the overrides to /etc.
# The path of the installed file depends on the build prefix: we detect it.

def resolve_base_path() -> Optional[str]:
    """Find the package-installed gamemode.ini (or None).

    Search order: the GAMEMODE_BASE variable (for tests), then $XDG_DATA_DIRS,
    finally /usr/local/share and /usr/share. Each candidate is
    ``<datadir>/gamemode/gamemode.ini``.
    """
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


def read_ini_comments(text: str) -> Dict[str, str]:
    """Extract the comments preceding each key: {"section.key": "; ..."}."""
    comments: Dict[str, str] = {}
    section = None
    pending: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            pending = []
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            pending = []
            continue
        if line.startswith(";") or line.startswith("#"):
            pending.append(line)
            continue
        if section and ("=" in line or ":" in line):
            sep = "=" if "=" in line else ":"
            name = line.split(sep, 1)[0].strip()
            if pending:
                comments[f"{section}.{name}"] = "\n".join(pending)
            pending = []
        else:
            pending = []
    return comments


def load_base_comments(path: Optional[str]) -> Dict[str, str]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return read_ini_comments(fh.read())
    except OSError:
        return {}


# ===========================================================================
# 4. SPECIAL VALUES (read from the system)
# ===========================================================================
# Some options (e.g. the CPU governor) have no static list of values: they must
# be derived from external factors. For these, `special` is true and
# `special_source` indicates the source.

_GOVERNORS_GLOB = "/sys/devices/system/cpu/cpu*/cpufreq/scaling_available_governors"
_FALLBACK_GOVERNORS = ["performance", "powersave", "ondemand", "conservative", "schedutil"]


def get_cpu_governors() -> List[str]:
    """List the CPU governors available on the system (with a static fallback).

    Scans all the CPUs' ``scaling_available_governors`` files (as GameMode does),
    so it works even with heterogeneous cpufreq policies (P-core/E-core,
    big.LITTLE) and on any distribution. A governor listed by several CPUs
    appears only once.
    """
    governors: List[str] = []
    for path in glob.glob(_GOVERNORS_GLOB):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for gov in fh.read().split():
                    if gov not in governors:
                        governors.append(gov)
        except OSError:
            continue
    return governors or list(_FALLBACK_GOVERNORS)


SPECIAL_SOURCES: Dict[str, Callable[[], List[str]]] = {
    "cpu_governors": get_cpu_governors,
}

_SYSFS_ONLINE = "/sys/devices/system/cpu/online"


def expand_cpu_list(text: str) -> List[int]:
    """Expand a Linux cpu-list (e.g. "0-3,8") into a list of integers."""
    cores: List[int] = []
    for token in str(text).split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, _, end = token.partition("-")
            try:
                cores.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                cores.append(int(token))
            except ValueError:
                pass
    return sorted(set(cores))


def get_cpu_cores() -> List[str]:
    """List the system's online cores (with an os.cpu_count fallback)."""
    try:
        with open(_SYSFS_ONLINE, "r", encoding="utf-8") as fh:
            cores = expand_cpu_list(fh.read().strip())
        if cores:
            return [str(c) for c in cores]
    except OSError:
        pass
    return [str(i) for i in range(os.cpu_count() or 1)]


SPECIAL_SOURCES["cpu_cores"] = get_cpu_cores


def resolve_choices(spec: OptionSpec) -> List[str]:
    """Allowed values for an option: static, or read from the system if special."""
    if spec.special:
        source = SPECIAL_SOURCES.get(spec.special_source or "")
        if source is not None:
            return source()
    return list(spec.choices or [])


# ===========================================================================
# 5. RENDERER (definitions + values -> gamemode.ini text)
# ===========================================================================

def escape_value(text: str) -> str:
    """Make a free text safe on a single INI line."""
    text = text.strip()
    text = " ".join(text.splitlines())
    if text.startswith(";") or text.startswith("#"):
        text = "\\" + text
    return text


# ---------------------------------------------------------------------------
# Type rules: a single dispatch table, per value_type, so the type logic is not
# scattered across the renderer, the parser and the coercion function.
#
# Each entry provides four callables:
#   render(spec, value)                              -> INI line(s)
#   is_written(spec, value)                          -> bool
#   parse_ini(spec, raw_values, existing, has_base)  -> value, or _MISSING
#   coerce_json(spec, raw)                           -> typed value (from the JSON session)
# ---------------------------------------------------------------------------

_MISSING = object()  # sentinel: parse_ini -> keep the existing value


def _render_bool(spec: OptionSpec, value) -> str:
    return spec.template.format(value=1 if value else 0)


def _render_cores(spec: OptionSpec, value) -> str:
    return spec.template.format(value=",".join(str(c) for c in value))


def _render_list(spec: OptionSpec, value) -> str:
    return "\n".join(spec.template.format(value=escape_value(item)) for item in value)


def _render_string(spec: OptionSpec, value) -> str:
    return spec.template.format(value=escape_value(str(value)))


def _render_default(spec: OptionSpec, value) -> str:
    return spec.template.format(value=value)


def _written_true_if_value(spec: OptionSpec, value) -> bool:
    return bool(value)


def _written_bool(spec: OptionSpec, value) -> bool:
    return bool(value) != bool(spec.default)


def _written_stringlike(spec: OptionSpec, value) -> bool:
    if value is None or str(value) == "":
        return False
    return str(value) != str(spec.default)


def _written_default(spec: OptionSpec, value) -> bool:
    return value is not None and value != spec.default


def _written_never(spec: OptionSpec, value) -> bool:
    return False


def _raw_text(raw_values: List[str]) -> str:
    return raw_values[-1] if len(raw_values) == 1 else ",".join(raw_values)


def _parse_int(spec: OptionSpec, raw_values: List[str], existing, has_base: bool):
    try:
        return int(_raw_text(raw_values))
    except ValueError:
        return _MISSING


def _parse_float(spec: OptionSpec, raw_values: List[str], existing, has_base: bool):
    try:
        return float(_raw_text(raw_values))
    except ValueError:
        return _MISSING


def _parse_bool(spec: OptionSpec, raw_values: List[str], existing, has_base: bool):
    return _raw_text(raw_values).strip() not in ("0", "false", "no")


def _parse_raw(spec: OptionSpec, raw_values: List[str], existing, has_base: bool):
    return _raw_text(raw_values)


def _parse_skip(spec: OptionSpec, raw_values: List[str], existing, has_base: bool):
    return _MISSING


def _parse_list(spec: OptionSpec, raw_values: List[str], existing, has_base: bool):
    parsed_list = [v.strip() for v in raw_values if v.strip()]
    if has_base and isinstance(existing, list):
        return existing + parsed_list
    return parsed_list


def _parse_cores(spec: OptionSpec, raw_values: List[str], existing, has_base: bool):
    return expand_cpu_list(",".join(raw_values))


def _coerce_int(spec: OptionSpec, raw):
    return int(raw)


def _coerce_float(spec: OptionSpec, raw):
    return float(raw)


def _coerce_bool(spec: OptionSpec, raw):
    return bool(raw)


def _coerce_raw(spec: OptionSpec, raw):
    return raw


def _coerce_list(spec: OptionSpec, raw):
    return list(raw) if isinstance(raw, list) else [str(raw)]


def _coerce_choice(spec: OptionSpec, raw):
    if spec.choices and raw not in spec.choices:
        return spec.default
    return raw


@dataclass(frozen=True)
class TypeRules:
    """Per-``value_type`` behaviour for rendering, parsing and coercion."""

    render: Callable[[OptionSpec, object], str]
    is_written: Callable[[OptionSpec, object], bool]
    parse_ini: Callable
    coerce_json: Callable[[OptionSpec, object], object]


TYPE_RULES: Dict[str, TypeRules] = {
    "bool": TypeRules(_render_bool, _written_bool, _parse_bool, _coerce_bool),
    "int": TypeRules(_render_default, _written_default, _parse_int, _coerce_int),
    "float": TypeRules(_render_default, _written_default, _parse_float, _coerce_float),
    "string": TypeRules(_render_string, _written_stringlike, _parse_raw, _coerce_raw),
    "choice": TypeRules(_render_default, _written_stringlike, _parse_raw, _coerce_choice),
    "enable": TypeRules(_render_default, _written_stringlike, _parse_raw, _coerce_raw),
    "list": TypeRules(_render_list, _written_true_if_value, _parse_list, _coerce_list),
    "cores": TypeRules(_render_cores, _written_true_if_value, _parse_cores, _coerce_raw),
    "toggle_entry": TypeRules(_render_default, _written_never, _parse_skip, _coerce_bool),
}
_DEFAULT_RULES = TypeRules(_render_default, _written_default, _parse_raw, _coerce_raw)


def _rules(spec: OptionSpec) -> TypeRules:
    return TYPE_RULES.get(spec.type, _DEFAULT_RULES)


def render_option(spec: OptionSpec, value) -> str:
    return _rules(spec).render(spec, value)


def is_written(spec: OptionSpec, value) -> bool:
    """True if the option must appear in the file.

    Options are written **only if active**, i.e. if their value differs from the
    default (or, for lists, if they are not empty). The type-specific rule lives
    in ``TYPE_RULES``.
    """
    return _rules(spec).is_written(spec, value)


def effective_list_value(spec: OptionSpec, values: Dict[str, object]) -> List[str]:
    """Effective list of a ``list`` option.

    Prepends the strings of the active ``toggle_entry`` options that have this
    list as their ``target`` (e.g. the start notification in ``start``).
    """
    items: List[str] = []
    for toggle in TOGGLE_ENTRIES_BY_TARGET.get(spec.id, ()):
        if values.get(toggle.id, toggle.default):
            items.append(toggle.entry)
    items.extend(values.get(spec.id) or [])
    return items


def dependency_met(spec: OptionSpec, values: Dict[str, object]) -> bool:
    """True if the option `spec` depends on is active."""
    if not spec.depends_on:
        return True
    dep_spec = OPTIONS_BY_ID.get(spec.depends_on)
    if dep_spec is None:
        return True
    return is_written(dep_spec, values.get(dep_spec.id, dep_spec.default))


def render_ini(values: Dict[str, object], comments: Optional[Dict[str, str]] = None) -> str:
    """Generate the content of the gamemode.ini file.

    For each category (in options.json order) it emits a comment + a formatted
    line **only for the active options** (value different from the default and
    dependency satisfied). Comments may come from the installed file
    (``comments``), with a fallback to the definition ones.
    """
    comments = comments or {}
    lines: list = []
    for section in SECTIONS_ORDER:
        section_lines = []
        for spec in OPTIONS_BY_SECTION.get(section, ()):
            if spec.type == "toggle_entry":
                continue  # it has no line of its own: it acts on the target list
            value = values.get(spec.id, spec.default)
            if spec.type == "list":
                value = effective_list_value(spec, values)
            if not dependency_met(spec, values):
                continue
            if not is_written(spec, value):
                continue
            comment = comments.get(spec.id, spec.comment)
            if comment:
                section_lines.append(comment)
            section_lines.append(render_option(spec, value))
        if section_lines:
            if lines:
                lines.append("")
            lines.append(f"[{section}]")
            lines.extend(section_lines)
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def default_values() -> Dict[str, object]:
    """Default values of all options."""
    return {spec.id: spec.default for spec in OPTIONS}


def default_ini() -> str:
    """File with all options at their default values (empty, with this logic)."""
    return render_ini(default_values())


# ===========================================================================
# 6. INI READING (keeps repeated keys for lists)
# ===========================================================================

def strip_inline_comment(value: str) -> str:
    for i, ch in enumerate(value):
        if ch in (";", "#") and (i == 0 or value[i - 1].isspace()):
            return value[:i].rstrip()
    return value


def parse_ini(text: str) -> Dict[str, Dict[str, List[str]]]:
    """Parse an INI text into section -> key -> [values]."""
    result: Dict[str, Dict[str, List[str]]] = {}
    section = None
    current_key = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            current_key = None
            result.setdefault(section, {})
            continue
        if section is None:
            continue
        if "=" in line or ":" in line:
            sep = "=" if "=" in line else ":"
            name, _, value = line.partition(sep)
            name = name.strip()
            value = strip_inline_comment(value.strip())
            current_key = name
            result[section].setdefault(name, []).append(value)
        elif current_key is not None:
            result[section].setdefault(current_key, []).append(
                strip_inline_comment(line))
    return result


def parse_ini_file(path: str) -> Dict[str, Dict[str, List[str]]]:
    with open(path, "r", encoding="utf-8") as fh:
        return parse_ini(fh.read())


# ===========================================================================
# 7. OPTION VALUES (in-memory state)
# ===========================================================================

def coerce_value(spec: OptionSpec, raw) -> object:
    """Convert a raw value (e.g. from the JSON session) to the spec type.

    On a value that cannot be converted or is not allowed, returns the spec
    default. The type-specific rule lives in ``TYPE_RULES``.
    """
    try:
        return _rules(spec).coerce_json(spec, raw)
    except (TypeError, ValueError):
        return spec.default


def values_from_parsed(parsed, base: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    """Build the current values from an already-parsed INI.

    With ``base`` it provides the starting values (e.g. from the installed
    file): the keys present in ``parsed`` override them, except lists which in
    GameMode are appended.
    """
    if base is not None:
        values: Dict[str, object] = dict(base)
    else:
        values = {spec.id: spec.default for spec in OPTIONS}
    for spec in OPTIONS:
        raw_values = parsed.get(spec.section, {}).get(spec.key)
        if not raw_values:
            continue
        value = _rules(spec).parse_ini(spec, raw_values, values.get(spec.id),
                                       base is not None)
        if value is not _MISSING:
            values[spec.id] = value
    return values


def load_values_from_file(path: Optional[str]) -> Dict[str, object]:
    """Read the values from a single file, filling in the defaults."""
    return load_effective_values(None, path)


def _extract_toggle_entries(values: Dict[str, object]) -> None:
    """Sync the ``toggle_entry`` switches with the lists read.

    If a list (e.g. ``custom.start``) contains the string managed by a switch,
    the switch is turned on and the string is removed from the list: the list
    then keeps only the "free" scripts, while the managed string is re-added at
    render time. This way there is a single source of truth for each.
    """
    for spec in OPTIONS:
        if spec.type != "toggle_entry" or not spec.target or not spec.entry:
            continue
        target = values.get(spec.target)
        if isinstance(target, list) and spec.entry in target:
            values[spec.id] = True
            values[spec.target] = [item for item in target if item != spec.entry]


def load_effective_values(base_path: Optional[str],
                          override_path: Optional[str]) -> Dict[str, object]:
    """Effective values = defaults, then installed file, then /etc override.

    Reproduces the daemon's merge order (lists are appended, scalar values are
    overridden).
    """
    values = default_values()
    for path in (base_path, override_path):
        if path and os.path.isfile(path):
            try:
                values = values_from_parsed(parse_ini_file(path), values)
            except OSError:
                pass
    _extract_toggle_entries(values)
    return values


# ===========================================================================
# 8. CONFIGURATION FILE MANAGEMENT (atomic write + backup)
# ===========================================================================
# - target in /etc/gamemode.ini: requires privileges => delegate to privileged.py
#   via pkexec (or sudo). Either way the operation is atomic and with rollback.
# - target on a writable path (e.g. .config for tests): local operation.

def _which(name: str, *fallbacks: str) -> Optional[str]:
    """Find an executable: first in the PATH, then among known absolute paths.

    Returns an absolute path, so the commands work even when the PATH is minimal
    (e.g. under ``pkexec``) or changes across distributions (``/usr/sbin`` vs
    ``/sbin``, merged-usr, etc.). ``None`` if not found.
    """
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
    pkexec = _which("pkexec", "/usr/bin/pkexec", "/usr/sbin/pkexec")
    if pkexec:
        prefixes.append([pkexec])
    sudo = _which("sudo", "/usr/bin/sudo", "/bin/sudo", "/usr/sbin/sudo")
    if sudo:
        prefixes.append([sudo, "-n"])
    return prefixes


def _privileged_argv(command: str, path: str,
                     extra_args: Optional[List[str]] = None) -> List[str]:
    """Build the command line for the privileged helper."""
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privileged.py")
    return [sys.executable, helper, command, path] + list(extra_args or [])


def run_privileged(command: str, path: str, content: str = "", timeout: int = 60,
                   extra_args: Optional[List[str]] = None) -> CommandResult:
    """Run a privileged operation trying pkexec then sudo (as a ``CommandResult``)."""
    argv = _privileged_argv(command, path, extra_args)
    for prefix in _privileged_prefixes():
        try:
            proc = subprocess.run(
                prefix + argv, input=content, capture_output=True,
                text=True, timeout=timeout, check=False)
            return CommandResult(proc.returncode == 0, proc.returncode,
                                 proc.stdout, proc.stderr,
                                 command=" ".join(prefix + argv))
        except FileNotFoundError:
            continue
        except subprocess.SubprocessError:
            continue
    raise FileNotFoundError("no privileged frontend available (pkexec/sudo)")


def is_privileged_path(path: str) -> bool:
    """True if the directory contains a non-writable root path (e.g. /etc)."""
    directory = os.path.dirname(path) or "/"
    return not os.access(directory, os.W_OK)


class ConfigManager:
    """Manage the gamemode.ini file: read, atomic commit, backup, rollback."""

    def __init__(self, config_path: str, orig_seed: str = "") -> None:
        self.config_path = config_path
        self.backup_path = config_path + ".bak"
        self.orig_path = config_path + ".orig"
        self.tmp_path = config_path + ".tmp"
        # Content of the installed file (base): used as ".orig" on the first
        # commit if the active file does not exist yet.
        self.orig_seed = orig_seed

    def read_existing(self) -> str:
        try:
            if os.path.isfile(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as fh:
                    return fh.read()
        except OSError:
            pass
        return ""

    def save(self, content: str) -> None:
        if is_privileged_path(self.config_path):
            extra_args: List[str] = []
            seed_file = self._write_seed_tmp()
            if seed_file:
                extra_args.append(seed_file)
            try:
                res = run_privileged("commit", self.config_path,
                                     content=content, extra_args=extra_args)
            finally:
                if seed_file:
                    try:
                        os.remove(seed_file)
                    except OSError:
                        pass
            if not res.success:
                detail = (res.stderr or res.stdout or "unknown error").strip()
                raise OSError(detail)
            return
        fileops.write_commit(self.config_path, content,
                             orig_seed_content=self.orig_seed, create_dirs=True)

    def _write_seed_tmp(self) -> Optional[str]:
        """Write the `.orig` seed to a temporary file readable by root."""
        if not self.orig_seed or os.path.isfile(self.orig_path):
            return None
        try:
            fd, path = tempfile.mkstemp(prefix="gamemode-orig-", suffix=".ini")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(self.orig_seed)
            os.chmod(path, 0o644)
            return path
        except OSError:
            return None

    def rollback_from_backup(self) -> bool:
        try:
            if is_privileged_path(self.config_path):
                return run_privileged("restore-backup", self.config_path).success
            fileops.restore_from_backup(self.config_path)
            return True
        except OSError:
            return False

    def restore_from_orig(self) -> bool:
        try:
            if is_privileged_path(self.config_path):
                return run_privileged("restore-orig", self.config_path).success
            fileops.restore_from_orig(self.config_path)
            return True
        except OSError:
            return False

    def ensure_orig_on_first_run(self) -> None:
        if os.path.isfile(self.orig_path):
            return
        if is_privileged_path(self.config_path):
            try:
                run_privileged("ensure-orig", self.config_path, content=default_ini())
            except Exception:
                pass
        else:
            try:
                directory = os.path.dirname(self.config_path) or "."
                os.makedirs(directory, mode=0o700, exist_ok=True)
                fileops.ensure_orig(self.config_path,
                                    seed_content=self.read_existing() or default_ini())
            except Exception:
                pass


# ===========================================================================
# 9. GAMEMODE UTILITIES (test, restart, group)
# ===========================================================================

@dataclass
class CommandResult:
    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    command: str = ""

    @property
    def output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout.rstrip())
        if self.stderr:
            parts.append(self.stderr.rstrip())
        if self.error:
            parts.append(self.error)
        return "\n".join(parts)


def _run(argv: List[str], timeout: int = 30) -> CommandResult:
    command = " ".join(argv)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, check=False)
        return CommandResult(proc.returncode == 0, proc.returncode,
                             proc.stdout, proc.stderr, command=command)
    except FileNotFoundError as exc:
        return CommandResult(False, -1, error=f"{tr('msg.cmd_not_found')}: {exc}",
                             command=command)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, -1, error=tr("msg.timeout"),
                             stdout=exc.stdout or "", stderr=exc.stderr or "",
                             command=command)
    except OSError as exc:
        return CommandResult(False, -1, error=str(exc), command=command)


def _gamemoded_path() -> Optional[str]:
    return _which("gamemoded", "/usr/bin/gamemoded", "/usr/local/bin/gamemoded")


def test_daemon() -> CommandResult:
    """Run the daemon diagnostic tests (``gamemoded -t``)."""
    gamemoded = _gamemoded_path()
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command="gamemoded -t")
    return _run([gamemoded, "-t"])


def daemon_version() -> CommandResult:
    """GameMode version (``gamemoded --version``).

    Note: ``gamemoderun --version`` is NOT used because ``gamemoderun`` is a
    script that execs the passed command (with LD_PRELOAD) and does not handle
    ``--version``: the version is printed by ``gamemoded``.
    """
    gamemoded = _gamemoded_path()
    if not gamemoded:
        return CommandResult(False, -1, error=tr("msg.gamemode_not_installed"),
                             command="gamemoded --version")
    return _run([gamemoded, "--version"])


def restart_daemon() -> CommandResult:
    """Restart gamemoded.

    GameMode installs ``gamemoded.service`` as a systemd **user** unit
    (``systemctl --user``). On systems with a system unit that one is also tried;
    without systemd it falls back to ``pkill`` (the daemon is D-Bus activated and
    restarts on the next request).
    """
    systemctl = _which("systemctl", "/usr/bin/systemctl", "/bin/systemctl")
    if systemctl:
        res_user = _run([systemctl, "--user", "restart", "gamemoded"])
        if res_user.success:
            return res_user
        res_system = _run([systemctl, "restart", "gamemoded"])
        return res_system if res_system.success else res_user
    pkill = _which("pkill", "/usr/bin/pkill", "/bin/pkill")
    if pkill:
        return _run([pkill, "-TERM", "gamemoded"])
    return CommandResult(False, -1, error=tr("msg.no_systemd"))


def group_exists() -> bool:
    try:
        grp.getgrnam("gamemode")
        return True
    except KeyError:
        return False


def user_in_group(user: Optional[str] = None) -> bool:
    user = user or getpass.getuser()
    if not group_exists():
        return False
    return user in list(grp.getgrnam("gamemode").gr_mem)


def add_user_to_group() -> CommandResult:
    """Add the user to the ``gamemode`` group (``usermod -aG``), with privileges."""
    user = getpass.getuser()
    usermod = _which("usermod", "/usr/sbin/usermod", "/sbin/usermod")
    if not usermod:
        return CommandResult(False, -1, error=tr("msg.usermod_missing"),
                             command=f"usermod -aG gamemode {user}")
    argv = [usermod, "-aG", "gamemode", user]
    last = CommandResult(False, -1, error=tr("msg.no_priv_frontend"),
                         command=" ".join(argv))
    for prefix in _privileged_prefixes():
        res = _run(prefix + argv, timeout=60)
        if res.success:
            return res
        last = res
    return last


# ===========================================================================
# 10. SESSION (value persistence on a JSON file, category structure)
# ===========================================================================
# The session has the same category structure as the definitions:
#     {"version": 1, "categories": {"general": {"reaper_freq": 10}, ...}}

def session_path(config_path: str) -> str:
    return config_path + ".session.json"


def save_session(config_path: str, values: Dict[str, object]) -> None:
    """Save the current values to <config>.session.json."""
    categories: Dict[str, Dict[str, object]] = {}
    for spec in OPTIONS:
        categories.setdefault(spec.section, {})[spec.key] = _json_safe(
            values.get(spec.id, spec.default))
    data = {"version": 1, "categories": categories}
    try:
        with open(session_path(config_path), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass


def _json_safe(value):
    if isinstance(value, (list, dict, str, int, float, bool)) or value is None:
        return value
    return str(value)


def load_session(config_path: str) -> Optional[Dict[str, object]]:
    """Reload the values (flat, id -> value) from session.json.

    Supports the new category format and the old
    ``{"flags": ..., "values": ...}`` format.
    """
    try:
        with open(session_path(config_path), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    categories = data.get("categories")
    if isinstance(categories, dict):
        flat: Dict[str, object] = {}
        for section, opts in categories.items():
            if isinstance(opts, dict):
                for key, value in opts.items():
                    flat[f"{section}.{key}"] = value
        return flat
    if isinstance(data.get("values"), dict):
        return data["values"]
    return None
