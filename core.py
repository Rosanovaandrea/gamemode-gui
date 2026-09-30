"""Core logico unificato della GUI di GameMode.

Questo modulo raccoglie TUTTA la logica non-GUI dell'applicazione, riducendo
il numero di file del progetto (refactoring richiesto):

  * tabella dichiarativa delle opzioni  (single source of truth)
  * renderer INI (tabella -> testo gamemode.ini)
  * lettura INI (conserva le liste ripetute)
  * flag di attivazione in memoria
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
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

    Il file XML ha questa forma:
        <translations>
          <entry id="window.title">GameMode GUI</entry>
        </translations>

    Se una chiave non esiste, viene restituita la chiave stessa (fallback
    visibile, mai un crash).
    """

    def __init__(self, lang: Optional[str] = None) -> None:
        self.lang = lang or _detect_lang()
        self._strings: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        path = os.path.join(_LOCALE_DIR, f"{self.lang}.xml")
        if not os.path.isfile(path):
            # Niente file per la lingua -> usa la lingua di default
            path = os.path.join(_LOCALE_DIR, f"{_DEFAULT_LANG}.xml")
        if not os.path.isfile(path):
            return
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
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
# 2. TABELLA DICHIARATIVA DELLE OPZIONI
# ===========================================================================
# Ogni opzione di gamemode.ini è descritta UNA volta, qui. L'ordine delle
# voci definisce l'ordine di scrittura nel file di output.


@dataclass(frozen=True)
class OptionSpec:
    """Descrizione di una singola chiave di una sezione INI."""

    section: str
    key: str
    type: str  # int | float | bool | string | choice | list
    default: Any
    template: str
    description: str
    choices: Optional[list] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unsafe: bool = False
    comment: str = ""  # commento emesso sopra l'opzione quando attiva
    standalone: bool = False  # chiavi senza valore, agganciate a un genitore

    @property
    def id(self) -> str:
        return f"{self.section}.{self.key}"


GOVERNORS = ["performance", "powersave", "ondemand", "conservative", "schedutil"]
PROFILES = ["performance", "low-power", "balanced"]
SOFT_REALTIME = ["auto", "on", "off"]
IOPRIO = ["0", "1", "2", "3", "4", "5", "6", "7", "off", "reset"]
AMD_LEVEL = ["auto", "low", "high", "manual"]


def _choice(section, key, choices, default, comment, description, unsafe=False):
    return OptionSpec(
        section=section, key=key, type="choice", choices=choices, default=default,
        template=f"{key}={{value}}", description=description, comment=comment,
        unsafe=unsafe,
    )


def _repeated_list(section, key, comment, description, unsafe=False):
    return OptionSpec(
        section=section, key=key, type="list", default=[],
        template=f"{key}={{value}}", description=description, comment=comment,
        unsafe=unsafe,
    )


OPTIONS: list = [
    # ---------------------------- [general] ------------------------------
    OptionSpec(
        section="general", key="reaper_freq", type="int", default=5, min_value=1,
        template="reaper_freq={value}",
        description=tr("opt.general.reaper_freq"),
        comment=("; The reaper thread will check every 5 seconds for exited "
                 "clients, for config file changes, and for the CPU/iGPU "
                 "power balance"),
    ),
    _choice("general", "desiredgov", GOVERNORS, "performance",
            "; The desired governor is used when entering GameMode instead of \"performance\"",
            tr("opt.general.desiredgov")),
    _choice("general", "defaultgov", GOVERNORS, "",
            ("; The default governor is used when leaving GameMode instead of "
             "restoring the original value"),
            tr("opt.general.defaultgov")),
    _choice("general", "desiredprof", PROFILES, "performance",
            "; The desired platform profile is used when entering GameMode instead of \"performance\"",
            tr("opt.general.desiredprof")),
    _choice("general", "defaultprof", PROFILES, "",
            ("; The default platform profile is used when leaving GameMode "
             "instead of restoring the original value"),
            tr("opt.general.defaultprof")),
    _choice("general", "igpu_desiredgov", GOVERNORS, "powersave",
            "; The iGPU desired governor is used when the integrated GPU is under heavy load",
            tr("opt.general.igpu_desiredgov")),
    OptionSpec(
        section="general", key="igpu_power_threshold", type="float",
        default=0.3, min_value=-1.0, max_value=1.0,
        template="igpu_power_threshold={value}",
        description=tr("opt.general.igpu_power_threshold"),
        comment="; Threshold to use to decide when the integrated GPU is under heavy load"),
    _choice("general", "softrealtime", SOFT_REALTIME, "off",
            "; GameMode can change the scheduler policy to SCHED_ISO on kernels which support it",
            tr("opt.general.softrealtime")),
    OptionSpec(
        section="general", key="renice", type="int", default=0,
        min_value=0, max_value=20, template="renice={value}",
        description=tr("opt.general.renice"),
        comment="; GameMode can renice game processes. You can put any value between 0 and 20 here"),
    OptionSpec(
        section="general", key="ioprio", type="choice", choices=IOPRIO,
        default="0", template="ioprio={value}",
        description=tr("opt.general.ioprio"),
        comment="; By default, GameMode adjusts the iopriority of clients to BE/0"),
    OptionSpec(
        section="general", key="inhibit_screensaver", type="bool", default=True,
        template="inhibit_screensaver={value}",
        description=tr("opt.general.inhibit_screensaver"),
        comment="; Sets whether gamemode will inhibit the screensaver when active"),
    OptionSpec(
        section="general", key="disable_splitlock", type="bool", default=True,
        template="disable_splitlock={value}",
        description=tr("opt.general.disable_splitlock"),
        comment="; Sets whether gamemode will disable split lock mitigation when active"),

    # ---------------------------- [filter] ------------------------------
    _repeated_list("filter", "whitelist",
                   comment=("; If \"whitelist\" entry has a value(s)\n"
                            "; gamemode will reject anything not in the whitelist"),
                   description=tr("opt.filter.whitelist")),
    _repeated_list("filter", "blacklist",
                   comment="; Gamemode will always reject anything in the blacklist",
                   description=tr("opt.filter.blacklist")),

    # ---------------------------- [gpu] ----------------------------------
    OptionSpec(
        section="gpu", key="apply_gpu_optimisations", type="choice",
        choices=["accept-responsibility", "0"], default="0",
        template="apply_gpu_optimisations={value}",
        description=tr("opt.gpu.apply_gpu_optimisations"),
        comment=("; Warning: Use these settings at your own risk. Any damage "
                 "to hardware is your responsibility and yours alone"),
        unsafe=True),
    OptionSpec(
        section="gpu", key="gpu_device", type="int", default=0, min_value=0,
        template="gpu_device={value}", description=tr("opt.gpu.gpu_device"),
        comment="; The DRM device number on the system (usually 0)", unsafe=True),
    OptionSpec(
        section="gpu", key="nv_powermizer_mode", type="choice",
        choices=["0", "1", "2"], default="1",
        template="nv_powermizer_mode={value}",
        description=tr("opt.gpu.nv_powermizer_mode"),
        comment=("; Nvidia specific settings\n"
                 "; Requires the coolbits extension activated in nvidia-xconfig"),
        unsafe=True),
    OptionSpec(
        section="gpu", key="nv_core_clock_mhz_offset", type="int", default=0,
        template="nv_core_clock_mhz_offset={value}",
        description=tr("opt.gpu.nv_core_clock_mhz_offset"), unsafe=True),
    OptionSpec(
        section="gpu", key="nv_mem_clock_mhz_offset", type="int", default=0,
        template="nv_mem_clock_mhz_offset={value}",
        description=tr("opt.gpu.nv_mem_clock_mhz_offset"), unsafe=True),
    _choice("gpu", "amd_performance_level", AMD_LEVEL, "high",
            comment=("; AMD specific settings\n"
                     "; Requires a relatively up to date AMDGPU kernel module"),
            description=tr("opt.gpu.amd_performance_level"), unsafe=True),
]

SECTIONS_ORDER = ["general", "filter", "gpu"]


def options_for_section(section: str) -> list:
    return [opt for opt in OPTIONS if opt.section == section and not opt.standalone]


# ===========================================================================
# 3. RENDERER (tabella dichiarativa -> testo gamemode.ini)
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
    if spec.type == "list":
        return "\n".join(spec.template.format(value=escape_value(item)) for item in value)
    if spec.type == "string":
        return spec.template.format(value=escape_value(str(value)))
    return spec.template.format(value=value)


def render_ini(flags: Dict[str, bool], values: Dict[str, object]) -> str:
    """Genera il contenuto completo del file gamemode.ini.

    Per ogni sezione (nell'ordine di SECTIONS_ORDER) e per ogni opzione attiva
    (flag True) emette commento + riga formattata. L'output è deterministico e
    sono preservati commenti e ordine dichiarati nella tabella.
    """
    lines: list = []
    for section in SECTIONS_ORDER:
        section_lines = []
        for spec in OPTIONS:
            if spec.section != section:
                continue
            if not flags.get(spec.id, False):
                continue
            value = values.get(spec.id, spec.default)
            if spec.type == "list" and not value:
                continue
            if spec.comment:
                section_lines.append(spec.comment)
            section_lines.append(render_option(spec, value))
        if section_lines:
            if lines:
                lines.append("")
            lines.append(f"[{section}]")
            lines.extend(section_lines)
    return "\n".join(lines) + "\n"


def default_ini() -> str:
    """Genera il file "di default" dalla tabella (tutte le opzioni attive)."""
    flags = {spec.id: True for spec in OPTIONS}
    values = {spec.id: spec.default for spec in OPTIONS}
    return render_ini(flags, values)


# ===========================================================================
# 4. LETTURA INI (conserva chiavi ripetute per le liste)
# ===========================================================================

def strip_inline_comment(value: str) -> str:
    for i, ch in enumerate(value):
        if ch in (";", "#") and (i == 0 or value[i - 1].isspace()):
            return value[:i].rstrip()
    return value


def parse_ini(text: str) -> Dict[str, Dict[str, List[str]]]:
    """Parsa un testo INI in section -> key -> [values].

    Usa liste di valori perché le chiavi ripetute (whitelist/blacklist) vanno
    preservate completamente.
    """
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
# 5. FLAG DI ATTIVAZIONE (stato in memoria delle scelte)
# ===========================================================================
# Le scelte dell'utente vivono in memoria come un dizionario di flag booleani
# + un dizionario di valori. Al commit vengono persistite su file. Ricostruiti
# all'avvio leggendo il file esistente (chiave presente => flag True).


class ActivationManager:
    def __init__(self) -> None:
        self._flags: Dict[str, bool] = {}

    def set_flag(self, option_id: str, enabled: bool) -> None:
        self._flags[option_id] = enabled

    def get_flag(self, option_id: str) -> bool:
        return self._flags.get(option_id, False)

    def enable(self, option_id: str) -> None:
        self._flags[option_id] = True

    def take_snapshot(self) -> Dict[str, bool]:
        return dict(self._flags)

    @staticmethod
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

    def rebuild_from_parsed(self, parsed) -> Dict[str, object]:
        values: Dict[str, object] = {}
        for spec in OPTIONS:
            raw_values = parsed.get(spec.section, {}).get(spec.key)
            if raw_values:
                self._flags[spec.id] = True
                if spec.type == "list":
                    values[spec.id] = [v.strip() for v in raw_values if v.strip()]
                else:
                    values[spec.id] = self._parse_scalar(spec.type, raw_values)
            else:
                self._flags[spec.id] = False
                values[spec.id] = spec.default
        return values

    def rebuild_from_file(self, path: Optional[str]) -> Dict[str, object]:
        if path is not None and os.path.isfile(path):
            try:
                return self.rebuild_from_parsed(parse_ini_file(path))
            except OSError:
                pass
        # Default (flag tutti False, valori di default)
        self._flags = {}
        values = {spec.id: spec.default for spec in OPTIONS}
        for spec in OPTIONS:
            self._flags[spec.id] = False
        return values


# ===========================================================================
# 6. GESTIONE FILE DI CONFIGURAZIONE (scrittura atomica + backup)
# ===========================================================================
# - target in /etc/gamemode.ini: richiede privilegi => delega a privileged.py
#   via pkexec (o sudo). In ogni caso l'operazione è atomica e con rollback.
# - target in un percorso scrivibile (es. .config per test): operazione locale.


def _privileged_argv(command: str, path: str) -> List[str]:
    """Costruisce la riga di comando per l'helper privilegiato."""
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privileged.py")
    return [sys.executable, helper, command, path]


def run_privileged(command: str, path: str, content: str = "", timeout: int = 60) -> subprocess.CompletedProcess:
    """Esegue un'operazione privilegiata provando pkexec poi sudo."""
    argv = _privileged_argv(command, path)
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
    """Gestisce il file gamemode.ini: lettura, commit atomico, backup, rollback.

    Il "commit" di un file in /etc riscrive TUTTO il file (copy-on-write su
    .tmp + os.replace); il file attivo precedente viene salvato in `.bak` e
    lo stato "vergine" iniziale in `.orig` (creato una sola volta).
    """

    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self.backup_path = config_path + ".bak"
        self.orig_path = config_path + ".orig"
        self.tmp_path = config_path + ".tmp"

    # -- lettura -----------------------------------------------------------
    def read_existing(self) -> str:
        """Restituisce il contenuto del file attivo, oppure stringa vuota."""
        try:
            if os.path.isfile(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as fh:
                    return fh.read()
        except OSError:
            pass
        return ""

    # -- commit ------------------------------------------------------------
    def save(self, content: str) -> None:
        """Salva `content` con strategia atomica+backup.

        In /etc delega a privileged.py (pkexec/sudo). A prescindere dal
        percorso l'operazione garantisce: .orig una volta, .bak del vecchio
        file, os.replace atomico, rollback su errore.
        Solleva OSError se il commit fallisce.
        """
        if is_privileged_path(self.config_path):
            proc = run_privileged("commit", self.config_path, content=content)
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "errore sconosciuto").strip()
                raise OSError(detail)
            return

        # Percorso scrivibile -> commit locale (stessa strategia del helper)
        self._save_local(content)

    def _save_local(self, content: str) -> None:
        directory = os.path.dirname(self.config_path) or "."
        os.makedirs(directory, mode=0o700, exist_ok=True)
        with open(self.tmp_path, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(self.tmp_path, 0o644)

        # .orig una sola volta
        if not os.path.isfile(self.orig_path):
            source = self.config_path if os.path.isfile(self.config_path) else self.tmp_path
            shutil.copy2(source, self.orig_path)
            os.chmod(self.orig_path, 0o644)

        # backup del precedente
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

    # -- ripristini ----------------------------------------------------------
    def rollback_from_backup(self) -> bool:
        """Ripristina `.bak` sul file attivo. True se riuscito."""
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
        """Ripristina `.orig` sul file attivo. True se riuscito."""
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
        """Crea `.orig` al primo avvio se non esiste (senza toccare l'attivo).

        Normalmente non serve chiamarlo: `.orig` viene creato automaticamente
        al primo commit. Questo metodo esiste per compatibilità/uso manuale.
        """
        if os.path.isfile(self.orig_path):
            return
        if is_privileged_path(self.config_path):
            try:
                run_privileged("ensure-orig", self.config_path,
                               content=default_ini())
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
# 7. UTILITY GAMEMODE (test, riavvio, gruppo)
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
# 8. SESSIONE (persistenza delle scelte su file di stato)
# ===========================================================================
# Le "indici delle scelte" (flag + valori) vengono mantenute in memoria durante
# la sessione e, al commit, salvate anche in un file JSON accanto alla
# configurazione attiva, così uno stato riapribile è disponibile anche se il
# file attivo viene modificato fuori dalla GUI.

def session_path(config_path: str) -> str:
    return config_path + ".session.json"


def save_session(config_path: str, flags: Dict[str, bool], values: Dict[str, object]) -> None:
    """Salva lo stato delle scelte correnti su <config>.session.json."""
    data = {
        "flags": flags,
        "values": {k: _json_safe(v) for k, v in values.items()},
    }
    try:
        with open(session_path(config_path), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass


def _json_safe(value):
    if isinstance(value, (list, dict, str, int, float, bool)) or value is None:
        return value
    return str(value)


def load_session(config_path: str) -> Optional[tuple]:
    """Ricarica flag+valori da session.json. Restituisce (flags, values) o None."""
    try:
        with open(session_path(config_path), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("flags", {}), data.get("values", {})
    except (OSError, ValueError):
        return None