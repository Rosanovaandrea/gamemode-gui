"""Core logico unificato della GUI di GameMode.

Questo modulo raccoglie TUTTA la logica non-GUI dell'applicazione:

  * caricamento delle definizioni delle opzioni da `options.json`
    (single source of truth: una voce JSON per opzione)
  * risoluzione dei valori "speciali" letti dal sistema (es. governor CPU)
  * renderer INI (definizioni + valori -> testo gamemode.ini)
  * lettura INI (conserva le liste ripetute)
  * gestione del file di configurazione (scrittura atomica, backup, rollback),
    sia nel percorso utente sia in /etc (via helper privilegiato)
  * utility per il daemon (test, riavvio, gruppo gamemode)
  * internazionalizzazione tramite file esterni XML (locale/<lang>.xml)

Nessuna dipendenza GTK qui dentro: la logica è testabile senza display.
"""

from __future__ import annotations

import getpass
import grp
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import fileops

# ===========================================================================
# 1. INTERNAZIONALIZZAZIONE (i18n)
# ===========================================================================
# La lingua è gestita tramite file esterni in `locale/<lang>.xml`.
#
# L'elenco delle lingue disponibili NON è hardcoded: si legge dalla chiave
# `supported_langs` del file impostazioni (settings.json), con fallback sui
# default italiano/inglese. Ogni voce viene validata: un codice senza file
# `locale/<codice>.xml` viene scartato e segnalato (vedi
# `describe_lang_errors()`), senza bloccare l'app.
#
# Ordine di priorità con cui si sceglie la lingua attiva:
#   1. scelta salvata dall'utente (`lang` in settings.json): precedenza su tutto;
#   2. locale di sistema (LC_ALL > LC_MESSAGES > LANG);
#   3. inglese ("en") come default.
#
# Niente stringhe hardcoded nel codice: si usa `tr("chiave")`.

_LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")
_DEFAULT_SUPPORTED_LANGS = ("it", "en")
_DEFAULT_LANG = "en"

try:
    import xml.etree.ElementTree as _ET
except Exception:  # pragma: no cover
    _ET = None

# Cache dell'elenco lingue validato + errori di configurazione. Gli errori sono
# coppie (tipo, dettaglio) formattabili con `describe_lang_errors()`: non si usa
# `tr()` qui perché verrebbe chiamato prima che il traduttore esista.
_langs_cache: Optional[tuple] = None
_langs_errors: List[tuple] = []


def normalize_lang_code(raw: object) -> Optional[str]:
    """Riduce un codice lingua alla forma breve minuscola (``it``, ``en``, …).

    Accetta ``it``, ``it_IT``, ``it_IT.UTF-8``, ``en-US`` e simili. NON verifica
    che la lingua sia supportata: lo fa `supported_lang`.
    """
    if not raw:
        return None
    code = str(raw).strip().lower()
    for sep in (".", "@"):
        code = code.split(sep, 1)[0]
    code = code.replace("-", "_").split("_", 1)[0]
    return code or None


def lang_file_path(code: str) -> str:
    """Percorso del file di lingua ``locale/<code>.xml``."""
    return os.path.join(_LOCALE_DIR, f"{code}.xml")


def _has_lang_file(code: str) -> bool:
    return os.path.isfile(lang_file_path(code))


def _compute_supported_langs() -> None:
    """Calcola una volta l'elenco lingue valido e registra gli errori di config.

    Errori possibili (coppie tipo/dettaglio):
      * ``bad_config``   → settings.json illeggibile o non un oggetto JSON;
      * ``bad_list``     → `supported_langs` non è una lista;
      * ``bad_entry``    → voce della lista non è un codice valido;
      * ``missing_file`` → lingua senza `locale/<codice>.xml`;
      * ``empty``        → nessuna lingua utilizzabile (fallback sull'inglese).
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

    # Se nessuna lingua configurata è utilizzabile, torna ai default sicuri.
    if not valid:
        for code in _DEFAULT_SUPPORTED_LANGS:
            if _has_lang_file(code) and code not in valid:
                valid.append(code)
        if not valid:
            errors.append(("empty", ""))

    _langs_cache = tuple(valid) if valid else (_DEFAULT_LANG,)
    _langs_errors = errors


def supported_langs() -> tuple:
    """Elenco lingue supportate: letto dalla config e validato sui file."""
    if _langs_cache is None:
        _compute_supported_langs()
    return _langs_cache


def reset_supported_langs() -> None:
    """Invalida la cache dell'elenco lingue (usato quando cambia la config)."""
    global _langs_cache
    _langs_cache = None


def lang_label(code: str) -> str:
    """Nome della lingua dall'attributo ``name`` del suo XML, o il codice maiuscolo."""
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
    """Coppie ``(codice, nome)`` per il menu, nell'ordine configurato."""
    return [(code, lang_label(code)) for code in supported_langs()]


def _fallback_lang() -> str:
    """Lingua di ripiego: il default se disponibile, altrimenti la prima valida."""
    langs = supported_langs()
    if _DEFAULT_LANG in langs:
        return _DEFAULT_LANG
    return langs[0] if langs else _DEFAULT_LANG


def supported_lang(raw: object) -> Optional[str]:
    """Codice normalizzato, solo se è una lingua supportata; altrimenti ``None``."""
    code = normalize_lang_code(raw)
    return code if code and code in supported_langs() else None


def detect_system_lang() -> str:
    """Lingua dal locale di sistema, con fallback sicuro.

    Rispetta la precedenza standard delle variabili d'ambiente
    (LC_ALL > LC_MESSAGES > LANG): vince la prima impostata; se non è una lingua
    supportata, si usa il fallback (inglese).
    """
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw = os.environ.get(var, "").strip()
        if raw:
            return supported_lang(raw) or _fallback_lang()
    return _fallback_lang()


# --- preferenza dell'utente (impostazioni dell'app) ------------------------
# Separata dal file gamemode.ini: è una preferenza dell'applicazione, non una
# opzione del daemon, e non deve finire in /etc.

# True se l'ultima lettura di settings.json è fallita (file rotto o non oggetto).
_settings_load_failed = False


def settings_dir() -> str:
    """Cartella delle impostazioni dell'utente (rispetta XDG_CONFIG_HOME)."""
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "gamemode-gui")


def settings_path() -> str:
    return os.path.join(settings_dir(), "settings.json")


def load_settings() -> Dict[str, object]:
    """Legge ``settings.json``; se assente o illeggibile restituisce ``{}``.

    In caso di file illeggibile o non oggetto JSON segnala l'errore (usato per
    avvisare l'utente) e prosegue con i default.
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
    """Scrive ``settings.json`` (best effort, mai fatale)."""
    try:
        os.makedirs(settings_dir(), mode=0o700, exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
    except OSError:
        pass


def ensure_settings() -> None:
    """Garantisce che settings.json esista e contenga ``supported_langs``.

    Il file viene creato al primo avvio con l'elenco lingue predefinito, così è
    direttamente leggibile/modificabile dall'utente.
    """
    settings = load_settings()
    if "supported_langs" not in settings:
        settings["supported_langs"] = list(_DEFAULT_SUPPORTED_LANGS)
        save_settings(settings)


def load_saved_lang() -> Optional[str]:
    """Lingua scelta dall'utente, se presente e supportata; altrimenti None."""
    return supported_lang(load_settings().get("lang"))


def save_lang(lang: str) -> None:
    """Salva la lingua scelta dall'utente (avrà la precedenza su tutto)."""
    code = supported_lang(lang) or _fallback_lang()
    settings = load_settings()
    settings.setdefault("supported_langs", list(_DEFAULT_SUPPORTED_LANGS))
    settings["lang"] = code
    save_settings(settings)


def resolve_lang() -> str:
    """Lingua effettiva: scelta salvata > locale di sistema > fallback."""
    return load_saved_lang() or detect_system_lang() or _fallback_lang()


class Translator:
    """Carica una tabella di traduzioni da un file XML e fornisce `tr()`.

    Se una chiave non esiste, viene restituita la chiave stessa (fallback
    visibile, mai un crash).
    """

    def __init__(self, lang: Optional[str] = None) -> None:
        self.lang = lang or resolve_lang()
        self._strings: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if _ET is None:
            return
        # Fallback a catena: lingua attiva → lingua di ripiego → default.
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
                # I file XML usano la sequenza "\n" per andare a capo.
                self._strings[key] = entry.text.strip().replace("\\n", "\n")

    def tr(self, key: str) -> str:
        return self._strings.get(key, key)


_translator = Translator()


def tr(key: str) -> str:
    """Traduci una chiave nella lingua corrente (predefinita: inglese)."""
    return _translator.tr(key)


def current_lang() -> str:
    """Codice della lingua attualmente attiva nel traduttore."""
    return _translator.lang


def describe_lang_errors() -> List[str]:
    """Messaggi localizzati sugli errori di configurazione delle lingue.

    Va chiamata a UI pronta (usa `tr`); gli errori grezzi sono in
    ``_langs_errors``, calcolati quando si legge l'elenco lingue.
    """
    supported_langs()  # assicura che gli errori siano stati calcolati
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
# 2. DEFINIZIONI DELLE OPZIONI (caricate da options.json)
# ===========================================================================
# Ogni opzione è descritta UNA volta, come voce JSON. I campi:
#
#   key             nome della chiave INI
#   description_id  chiave i18n della descrizione
#   label_id        (opzionale) chiave i18n del nome visibile (default: key)
#   value_type      int | float | bool | string | choice | list | cores | enable | toggle_entry
#   widget          stepper | switch | radio | list | cores | entry
#   range           [min, max] per i numerici (null = illimitato)
#   choices         valori ammessi per value_type "choice"
#   default         valore di default
#   special         true se i valori vanno letti dal sistema
#   special_source  sorgente per i valori speciali (es. "cpu_governors")
#   on_value        per value_type "enable": valore scritto quando è attivo
#   depends_on      id di un'altra opzione da cui questa dipende
#   comment         commento emesso nel file INI sopra l'opzione
#   target/entry    per value_type "toggle_entry": l'interruttore aggiunge/rimuove
#                   la stringa `entry` dalla lista `target` (es. notifica in start)
#
# A livello di categoria, `toggle_card_id` è la chiave i18n del titolo della card
# che raccoglie le opzioni "toggle_entry" in cima alla scheda.

_OPTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "options.json")


@dataclass(frozen=True)
class OptionSpec:
    """Descrizione di una singola chiave di una sezione INI."""

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
    """Categoria (sezione INI + scheda) con le sue opzioni."""

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
    """Carica le categorie e le opzioni da ``options.json``."""
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

# Opzioni raggruppate per sezione, nell'ordine di options.json (usato dal renderer).
OPTIONS_BY_SECTION: Dict[str, List[OptionSpec]] = {section: [] for section in SECTIONS_ORDER}
for _spec in OPTIONS:
    OPTIONS_BY_SECTION.setdefault(_spec.section, []).append(_spec)

# Opzioni "toggle_entry" raggruppate per lista bersaglio (es. custom.start).
TOGGLE_ENTRIES_BY_TARGET: Dict[str, List[OptionSpec]] = {}
for _spec in OPTIONS:
    if _spec.type == "toggle_entry" and _spec.target:
        TOGGLE_ENTRIES_BY_TARGET.setdefault(_spec.target, []).append(_spec)


# ===========================================================================
# 2b. PRESENTAZIONE (contenuti data-driven, come options.json)
# ===========================================================================
# La scheda "Presentazione" non contiene opzioni: è una pagina di testo divisa
# in blocchi. La struttura (quali blocchi, in che ordine, quali sono di avviso)
# vive in presentation.json, mentre i testi veri stanno nei file di lingua
# (approccio data-driven + i18n). Aggiungere un blocco = voce JSON + chiavi i18n.

_PRESENTATION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "presentation.json")


@dataclass(frozen=True)
class PresentationBlock:
    """Un blocco della presentazione: titolo + testo (+ eventuale avviso)."""

    id: str
    heading_id: str
    body_id: str
    warning: bool = False


@dataclass(frozen=True)
class Presentation:
    """Contenuto della scheda Presentazione (titolo, sottotitolo, blocchi)."""

    title_id: str
    subtitle_id: str
    blocks: tuple


def load_presentation(path: str = _PRESENTATION_FILE) -> Presentation:
    """Carica i blocchi della Presentazione da ``presentation.json``."""
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
# 3. PERCORSI DI CONFIGURAZIONE (ordine di caricamento del daemon)
# ===========================================================================
# GameMode carica in quest'ordine e fonde:
#   1. <datadir>/gamemode/gamemode.ini   (file installato dal pacchetto, "base")
#   2. /etc/gamemode.ini                 (override dell'amministratore)
#   3. ~/.config/gamemode.ini            (utente)
#   4. $PWD/gamemode.ini                 (locale)
# La GUI usa il file installato come "base" e scrive gli override in /etc.
# Il percorso del file installato dipende dal prefix di build: lo rileviamo.

def resolve_base_path() -> Optional[str]:
    """Individua il gamemode.ini installato dal pacchetto (o None).

    Ordine di ricerca: variabile GAMEMODE_BASE (per i test), poi
    $XDG_DATA_DIRS, infine /usr/local/share e /usr/share. Ogni candidate è
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
    """Estrae i commenti che precedono ogni chiave: {"section.key": "; ..."}."""
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
# 4. VALORI SPECIALI (letti dal sistema)
# ===========================================================================
# Alcune opzioni (es. il governor CPU) non hanno una lista statica di valori:
# vanno ricavate da fattori esterni. Per queste `special` è true e
# `special_source` indica la sorgente.

_SYSFS_GOVERNORS = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors"
_FALLBACK_GOVERNORS = ["performance", "powersave", "ondemand", "conservative", "schedutil"]


def get_cpu_governors() -> List[str]:
    """Elenca i governor CPU disponibili sul sistema (con fallback statico)."""
    try:
        with open(_SYSFS_GOVERNORS, "r", encoding="utf-8") as fh:
            governors = fh.read().split()
        if governors:
            return governors
    except OSError:
        pass
    return list(_FALLBACK_GOVERNORS)


SPECIAL_SOURCES: Dict[str, Callable[[], List[str]]] = {
    "cpu_governors": get_cpu_governors,
}

_SYSFS_ONLINE = "/sys/devices/system/cpu/online"


def expand_cpu_list(text: str) -> List[int]:
    """Espande una cpu-list di Linux (es. "0-3,8") in una lista di interi."""
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
    """Elenca i core online del sistema (con fallback su os.cpu_count)."""
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
    """Valori ammessi per un'opzione: statici o letti dal sistema se special."""
    if spec.special:
        source = SPECIAL_SOURCES.get(spec.special_source or "")
        if source is not None:
            return source()
    return list(spec.choices or [])


# ===========================================================================
# 5. RENDERER (definizioni + valori -> testo gamemode.ini)
# ===========================================================================

def escape_value(text: str) -> str:
    """Rende un testo libero sicuro su una singola riga INI."""
    text = text.strip()
    text = " ".join(text.splitlines())
    if text.startswith(";") or text.startswith("#"):
        text = "\\" + text
    return text


def render_option(spec: OptionSpec, value) -> str:
    if spec.type == "bool":
        return spec.template.format(value=1 if value else 0)
    if spec.type == "cores":
        return spec.template.format(value=",".join(str(c) for c in value))
    if spec.type == "list":
        return "\n".join(spec.template.format(value=escape_value(item)) for item in value)
    if spec.type == "string":
        return spec.template.format(value=escape_value(str(value)))
    return spec.template.format(value=value)


def is_written(spec: OptionSpec, value) -> bool:
    """True se l'opzione deve comparire nel file.

    Le opzioni vengono scritte **solo se attive**, cioè se il loro valore
    differisce dal default (o, per le liste, se non sono vuote). I default non
    vengono scritti perché GameMode li applica già da sé.
    """
    if spec.type == "toggle_entry":
        return False
    if spec.type in ("list", "cores"):
        return bool(value)
    if spec.type == "bool":
        return bool(value) != bool(spec.default)
    if spec.type in ("string", "choice", "enable"):
        if value is None or str(value) == "":
            return False
        return str(value) != str(spec.default)
    return value is not None and value != spec.default


def effective_list_value(spec: OptionSpec, values: Dict[str, object]) -> List[str]:
    """Lista effettiva di un'opzione ``list``.

    Aggiunge in testa le stringhe delle opzioni ``toggle_entry`` attive che
    hanno questa lista come ``target`` (es. la notifica di avvio in ``start``).
    """
    items: List[str] = []
    for toggle in TOGGLE_ENTRIES_BY_TARGET.get(spec.id, ()):
        if values.get(toggle.id, toggle.default):
            items.append(toggle.entry)
    items.extend(values.get(spec.id) or [])
    return items


def dependency_met(spec: OptionSpec, values: Dict[str, object]) -> bool:
    """True se l'eventuale opzione da cui `spec` dipende è attiva."""
    if not spec.depends_on:
        return True
    dep_spec = OPTIONS_BY_ID.get(spec.depends_on)
    if dep_spec is None:
        return True
    return is_written(dep_spec, values.get(dep_spec.id, dep_spec.default))


def render_ini(values: Dict[str, object], comments: Optional[Dict[str, str]] = None) -> str:
    """Genera il contenuto del file gamemode.ini.

    Per ogni categoria (nell'ordine di options.json) emette commento + riga
    formattata **solo per le opzioni attive** (valore diverso dal default e
    dipendenza soddisfatta). I commenti possono arrivare dal file installato
    (``comments``), con fallback su quelli della definizione.
    """
    comments = comments or {}
    lines: list = []
    for section in SECTIONS_ORDER:
        section_lines = []
        for spec in OPTIONS_BY_SECTION.get(section, ()):
            if spec.type == "toggle_entry":
                continue  # non ha una propria riga: agisce sulla lista target
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
    """Valori di default di tutte le opzioni."""
    return {spec.id: spec.default for spec in OPTIONS}


def default_ini() -> str:
    """File con tutte le opzioni ai valori di default (vuoto, con questa logica)."""
    return render_ini(default_values())


# ===========================================================================
# 6. LETTURA INI (conserva chiavi ripetute per le liste)
# ===========================================================================

def strip_inline_comment(value: str) -> str:
    for i, ch in enumerate(value):
        if ch in (";", "#") and (i == 0 or value[i - 1].isspace()):
            return value[:i].rstrip()
    return value


def parse_ini(text: str) -> Dict[str, Dict[str, List[str]]]:
    """Parsa un testo INI in section -> key -> [values]."""
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
# 7. VALORI DELLE OPZIONI (stato in memoria)
# ===========================================================================

def _parse_scalar(kind: str, raw_list: List[str]) -> object:
    if not raw_list:
        return None
    raw = raw_list[-1] if len(raw_list) == 1 else ",".join(raw_list)
    try:
        if kind == "int":
            return int(raw)
        if kind == "float":
            return float(raw)
        if kind == "bool":
            return raw.strip() not in ("0", "false", "no")
    except ValueError:
        return None
    return raw


def coerce_value(spec: OptionSpec, raw) -> object:
    """Converte un valore grezzo (es. da sessione JSON) al tipo della spec.

    In caso di valore non convertibile o non ammesso restituisce il default
    della spec: è l'equivalente "di tipo" di `values_from_parsed`, ma per dati
    già tipizzati (JSON) invece che testo INI.
    """
    try:
        if spec.type == "int":
            return int(raw)
        if spec.type == "float":
            return float(raw)
        if spec.type in ("bool", "toggle_entry"):
            return bool(raw)
        if spec.type == "list":
            return list(raw) if isinstance(raw, list) else [str(raw)]
        if spec.type == "choice" and spec.choices and raw not in spec.choices:
            return spec.default
        return raw
    except (TypeError, ValueError):
        return spec.default


def values_from_parsed(parsed, base: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    """Costruisce i valori correnti a partire da un INI già parsato.

    Con ``base`` fornisce i valori di partenza (es. dal file installato): le
    chiavi presenti in ``parsed`` li sovrascrivono, tranne le liste che in
    GameMode si accodano.
    """
    if base is not None:
        values: Dict[str, object] = dict(base)
    else:
        values = {spec.id: spec.default for spec in OPTIONS}
    for spec in OPTIONS:
        raw_values = parsed.get(spec.section, {}).get(spec.key)
        if not raw_values:
            continue
        if spec.type == "list":
            parsed_list = [v.strip() for v in raw_values if v.strip()]
            existing = values.get(spec.id)
            if base is not None and isinstance(existing, list):
                values[spec.id] = existing + parsed_list
            else:
                values[spec.id] = parsed_list
        elif spec.type == "cores":
            values[spec.id] = expand_cpu_list(",".join(raw_values))
        else:
            parsed_value = _parse_scalar(spec.type, raw_values)
            if parsed_value is not None:
                values[spec.id] = parsed_value
            elif base is None:
                values[spec.id] = spec.default
    return values


def load_values_from_file(path: Optional[str]) -> Dict[str, object]:
    """Legge i valori da un singolo file, completando con i default."""
    return load_effective_values(None, path)


def _extract_toggle_entries(values: Dict[str, object]) -> None:
    """Sincronizza gli interruttori ``toggle_entry`` con le liste lette.

    Se una lista (es. ``custom.start``) contiene la stringa gestita da un
    interruttore, l'interruttore viene acceso e la stringa rimossa dalla lista:
    la lista resta così solo gli script "liberi", mentre la stringa gestita
    viene riaggiunta al render. Così c'è una sola fonte di verità per ciascuna.
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
    """Valori effettivi = default, poi file installato, poi override /etc.

    Riproduce l'ordine di merge del daemon (le liste si accodano, i valori
    scalari vengono sovrascritti).
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
# 8. GESTIONE FILE DI CONFIGURAZIONE (scrittura atomica + backup)
# ===========================================================================
# - target in /etc/gamemode.ini: richiede privilegi => delega a privileged.py
#   via pkexec (o sudo). In ogni caso l'operazione è atomica e con rollback.
# - target in un percorso scrivibile (es. .config per test): operazione locale.

def _privileged_argv(command: str, path: str,
                     extra_args: Optional[List[str]] = None) -> List[str]:
    """Costruisce la riga di comando per l'helper privilegiato."""
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privileged.py")
    return [sys.executable, helper, command, path] + list(extra_args or [])


def run_privileged(command: str, path: str, content: str = "", timeout: int = 60,
                   extra_args: Optional[List[str]] = None) -> subprocess.CompletedProcess:
    """Esegue un'operazione privilegiata provando pkexec poi sudo."""
    argv = _privileged_argv(command, path, extra_args)
    for prefix in (["pkexec"], ["sudo", "-n"]):
        try:
            return subprocess.run(
                prefix + argv, input=content, capture_output=True,
                text=True, timeout=timeout, check=False)
        except FileNotFoundError:
            continue
        except subprocess.SubprocessError:
            continue
    raise FileNotFoundError("nessun frontend privilegiato disponibile (pkexec/sudo)")


def is_privileged_path(path: str) -> bool:
    """True se la directory contiene una root path (es. /etc) non scrivibile."""
    directory = os.path.dirname(path) or "/"
    return not os.access(directory, os.W_OK)


class ConfigManager:
    """Gestisce il file gamemode.ini: lettura, commit atomico, backup, rollback."""

    def __init__(self, config_path: str, orig_seed: str = "") -> None:
        self.config_path = config_path
        self.backup_path = config_path + ".bak"
        self.orig_path = config_path + ".orig"
        self.tmp_path = config_path + ".tmp"
        # Contenuto del file installato (base): usato come ".orig" al primo
        # commit se il file attivo non esiste ancora.
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
                proc = run_privileged("commit", self.config_path,
                                      content=content, extra_args=extra_args)
            finally:
                if seed_file:
                    try:
                        os.remove(seed_file)
                    except OSError:
                        pass
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "errore sconosciuto").strip()
                raise OSError(detail)
            return
        self._save_local(content)

    def _write_seed_tmp(self) -> Optional[str]:
        """Scrive il seed `.orig` in un file temporaneo leggibile da root."""
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

    def _save_local(self, content: str) -> None:
        """Commit atomico sul percorso locale (logica condivisa in fileops)."""
        fileops.write_commit(self.config_path, content,
                             orig_seed_content=self.orig_seed, create_dirs=True)

    def rollback_from_backup(self) -> bool:
        try:
            if is_privileged_path(self.config_path):
                proc = run_privileged("restore-backup", self.config_path)
                return proc.returncode == 0
            fileops.restore_from_backup(self.config_path)
            return True
        except OSError:
            return False

    def restore_from_orig(self) -> bool:
        try:
            if is_privileged_path(self.config_path):
                proc = run_privileged("restore-orig", self.config_path)
                return proc.returncode == 0
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
# 9. UTILITY GAMEMODE (test, riavvio, gruppo)
# ===========================================================================

@dataclass
class CommandResult:
    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""

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
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, check=False)
        return CommandResult(proc.returncode == 0, proc.returncode,
                             proc.stdout, proc.stderr)
    except FileNotFoundError as exc:
        return CommandResult(False, -1, error=f"{tr('msg.cmd_not_found')}: {exc}")
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, -1, error=tr("msg.timeout"),
                             stdout=exc.stdout or "", stderr=exc.stderr or "")
    except OSError as exc:
        return CommandResult(False, -1, error=str(exc))


def test_daemon() -> CommandResult:
    return _run(["gamemoded", "-t"])


def daemon_version() -> CommandResult:
    return _run(["gamemoderun", "--version"])


def restart_daemon() -> CommandResult:
    return _run(["systemctl", "--user", "restart", "gamemoded"])


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
    user = getpass.getuser()
    argv = ["usermod", "-aG", "gamemode", user]
    for prefix in (["pkexec"], ["sudo", "-n"]):
        try:
            return _run(prefix + argv, timeout=60)
        except subprocess.SubprocessError:
            continue
    return CommandResult(False, -1, error=tr("msg.no_priv_frontend"))


# ===========================================================================
# 10. SESSIONE (persistenza dei valori su file JSON, struttura a categorie)
# ===========================================================================
# La sessione ha la stessa struttura a categorie delle definizioni:
#     {"version": 1, "categories": {"general": {"reaper_freq": 10}, ...}}

def session_path(config_path: str) -> str:
    return config_path + ".session.json"


def save_session(config_path: str, values: Dict[str, object]) -> None:
    """Salva i valori correnti su <config>.session.json."""
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
    """Ricarica i valori (piatti, id -> valore) da session.json.

    Supporta il nuovo formato a categorie e il vecchio formato
    ``{"flags": ..., "values": ...}``.
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
