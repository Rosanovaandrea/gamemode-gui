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
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# ===========================================================================
# 1. INTERNAZIONALIZZAZIONE (i18n)
# ===========================================================================
# La lingua è gestita tramite file esterni in `locale/<lang>.xml`. Attualmente
# esiste solo l'italiano, ma il sistema è configurabile: basta aggiungere un
# altro file XML (es. locale/en.xml) e selezionare la lingua con la variabile
# d'ambiente GAMEMODE_LANG o con il rilevamento automatico di sistema.
# Niente stringhe hardcoded nel codice: si usa `tr("chiave")`.

_LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")
_DEFAULT_LANG = "it"

try:
    import xml.etree.ElementTree as _ET
except Exception:  # pragma: no cover
    _ET = None


def _detect_lang() -> str:
    """Lingua richiesta: variabile d'ambiente sovrascrive il sistema."""
    env = os.environ.get("GAMEMODE_LANG", "").strip()
    if env:
        return env
    try:
        import locale
        code, _ = locale.getdefaultlocale(("LANG", "LC_ALL"))
        if code:
            return code.split("_")[0]
    except Exception:
        pass
    return _DEFAULT_LANG


class Translator:
    """Carica una tabella di traduzioni da un file XML e fornisce `tr()`.

    Se una chiave non esiste, viene restituita la chiave stessa (fallback
    visibile, mai un crash).
    """

    def __init__(self, lang: Optional[str] = None) -> None:
        self.lang = lang or _detect_lang()
        self._strings: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if _ET is None:
            return
        path = os.path.join(_LOCALE_DIR, f"{self.lang}.xml")
        if not os.path.isfile(path):
            path = os.path.join(_LOCALE_DIR, f"{_DEFAULT_LANG}.xml")
        if not os.path.isfile(path):
            return
        try:
            root = _ET.parse(path).getroot()
        except Exception:
            return
        for entry in root.findall("entry"):
            key = entry.get("id")
            if key is not None and entry.text:
                self._strings[key] = entry.text.strip()

    def tr(self, key: str) -> str:
        return self._strings.get(key, key)


_translator = Translator()


def tr(key: str) -> str:
    """Traduci una chiave nella lingua corrente (predefinita: italiano)."""
    return _translator.tr(key)


# ===========================================================================
# 2. DEFINIZIONI DELLE OPZIONI (caricate da options.json)
# ===========================================================================
# Ogni opzione è descritta UNA volta, come voce JSON. I campi:
#
#   key             nome della chiave INI
#   description_id  chiave i18n della descrizione
#   label_id        (opzionale) chiave i18n del nome visibile (default: key)
#   value_type      int | float | bool | string | choice | list | enable
#   widget          stepper | switch | radio | list | entry
#   range           [min, max] per i numerici (null = illimitato)
#   choices         valori ammessi per value_type "choice"
#   default         valore di default
#   special         true se i valori vanno letti dal sistema
#   special_source  sorgente per i valori speciali (es. "cpu_governors")
#   on_value        per value_type "enable": valore scritto quando è attivo
#   depends_on      id di un'altra opzione da cui questa dipende
#   comment         commento emesso nel file INI sopra l'opzione

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
        ))
    return categories


CATEGORIES: List[Category] = load_categories()
OPTIONS: List[OptionSpec] = [spec for cat in CATEGORIES for spec in cat.options]
SECTIONS_ORDER: List[str] = [cat.id for cat in CATEGORIES]
OPTIONS_BY_ID: Dict[str, OptionSpec] = {spec.id: spec for spec in OPTIONS}


def options_for_section(section: str) -> list:
    return [opt for opt in OPTIONS if opt.section == section]


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
    if spec.type in ("list", "cores"):
        return bool(value)
    if spec.type == "bool":
        return bool(value) != bool(spec.default)
    if spec.type in ("string", "choice", "enable"):
        if value is None or str(value) == "":
            return False
        return str(value) != str(spec.default)
    return value is not None and value != spec.default


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
        for spec in OPTIONS:
            if spec.section != section:
                continue
            value = values.get(spec.id, spec.default)
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
        directory = os.path.dirname(self.config_path) or "."
        os.makedirs(directory, mode=0o700, exist_ok=True)
        with open(self.tmp_path, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(self.tmp_path, 0o644)

        if not os.path.isfile(self.orig_path):
            if os.path.isfile(self.config_path):
                shutil.copy2(self.config_path, self.orig_path)
            elif self.orig_seed:
                with open(self.orig_path, "w", encoding="utf-8") as fh:
                    fh.write(self.orig_seed)
            else:
                shutil.copy2(self.tmp_path, self.orig_path)
            os.chmod(self.orig_path, 0o644)

        had_previous = os.path.isfile(self.config_path)
        if had_previous:
            shutil.copy2(self.config_path, self.backup_path)

        try:
            os.replace(self.tmp_path, self.config_path)
        except OSError:
            if had_previous and os.path.isfile(self.backup_path):
                shutil.copy2(self.backup_path, self.config_path)
            raise

        os.chmod(self.config_path, 0o644)
        if os.path.exists(self.tmp_path):
            try:
                os.remove(self.tmp_path)
            except OSError:
                pass

    def rollback_from_backup(self) -> bool:
        try:
            if is_privileged_path(self.config_path):
                proc = run_privileged("restore-backup", self.config_path)
                return proc.returncode == 0
            if not os.path.isfile(self.backup_path):
                return False
            shutil.copy2(self.backup_path, self.config_path)
            os.chmod(self.config_path, 0o644)
            return True
        except OSError:
            return False

    def restore_from_orig(self) -> bool:
        try:
            if is_privileged_path(self.config_path):
                proc = run_privileged("restore-orig", self.config_path)
                return proc.returncode == 0
            if not os.path.isfile(self.orig_path):
                return False
            shutil.copy2(self.orig_path, self.config_path)
            os.chmod(self.config_path, 0o644)
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
                if not os.path.isfile(self.orig_path):
                    with open(self.orig_path, "w", encoding="utf-8") as fh:
                        fh.write(self.read_existing() or default_ini())
                    os.chmod(self.orig_path, 0o644)
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
