"""Declarative table of every option in ``gamemode.ini``.

This module is the *single source of truth* for the whole application.
Every option that the GUI can manage is described once, here, as an
:class:`OptionSpec` (or a :class:`CommentSpec` for free-form comments).

Adding a new option to the application means appending one entry to
``OPTIONS`` -- nothing else needs to change in the rest of the codebase.

Defaults and value ranges were derived from the reference implementation
(``daemon/gamemode-config.c``) so that the generated file is valid for the
freedesktop GameMode daemon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class OptionSpec:
    """Description of a single ``key`` inside an INI ``section``."""

    section: str
    key: str
    type: str  # one of: int, float, bool, string, choice, list
    default: Any
    template: str
    description: str
    choices: Optional[list] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unsafe: bool = False
    # A comment emitted above the option when it is active. It is rendered
    # verbatim (the leading ``;`` is included) so it is preserved across
    # saves thanks to the tabular approach.
    comment: str = ""
    # Keys that never get a value of their own (e.g. free-text entries that
    # only make sense when their parent option is enabled).
    standalone: bool = False

    @property
    def id(self) -> str:
        return f"{self.section}.{self.key}"


@dataclass(frozen=True)
class CommentSpec:
    """A free-form comment to always emit inside a section."""

    section: str
    comment: str


# --------------------------------------------------------------------------
# Shared choice sets
# --------------------------------------------------------------------------
GOVERNORS = ["performance", "powersave", "ondemand", "conservative", "schedutil"]
PROFILES = ["performance", "low-power", "balanced"]
SOFT_REALTIME = ["auto", "on", "off"]
IOPRIO = ["0", "1", "2", "3", "4", "5", "6", "7", "off", "reset"]
AMD_LEVEL = ["auto", "low", "high", "manual"]
X3D_MODE = ["frequency", "cache"]


def _choice(section, key, choices, default, comment, description, unsafe=False,
            template=None):
    """Convenience constructor for a ``choice`` option."""
    return OptionSpec(
        section=section,
        key=key,
        type="choice",
        choices=choices,
        default=default,
        template=template or f"{key}={{value}}",
        description=description,
        comment=comment,
        unsafe=unsafe,
    )


def _repeated_list(section, key, comment, description, unsafe=False):
    """Convenience constructor for a list option stored as repeated keys."""
    return OptionSpec(
        section=section,
        key=key,
        type="list",
        default=[],
        template=f"{key}={{value}}",
        description=description,
        comment=comment,
        unsafe=unsafe,
    )


# --------------------------------------------------------------------------
# The table itself. Order matters: it defines the order of the output file.
# --------------------------------------------------------------------------
OPTIONS: list = [
    # ------------------------------------------------------------------
    # [general]
    # ------------------------------------------------------------------
    OptionSpec(
        section="general",
        key="reaper_freq",
        type="int",
        default=5,
        min_value=1,
        template="reaper_freq={value}",
        description=("Frequenza del thread reaper in secondi (controlla "
                     "l'uscita dei client, le modifiche al file e il "
                     "bilanciamento CPU/iGPU)."),
        comment=("; The reaper thread will check every 5 seconds for exited "
                 "clients, for config file changes, and for the CPU/iGPU "
                 "power balance"),
    ),
    _choice(
        "general", "desiredgov", GOVERNORS, "performance",
        "; The desired governor is used when entering GameMode instead of \"performance\"",
        ("Governor desiderato usato all'ingresso in GameMode."),
    ),
    _choice(
        "general", "defaultgov", GOVERNORS, "",
        ("; The default governor is used when leaving GameMode instead of "
         "restoring the original value"),
        ("Governor ripristinato all'uscita da GameMode invece del valore "
         "originale. Se non impostato, viene ripristinato il precedente."),
    ),
    _choice(
        "general", "desiredprof", PROFILES, "performance",
        "; The desired platform profile is used when entering GameMode instead of \"performance\"",
        ("Profilo di piattaforma desiderato all'ingresso in GameMode."),
    ),
    _choice(
        "general", "defaultprof", PROFILES, "",
        ("; The default platform profile is used when leaving GameMode "
         "instead of restoring the original value"),
        ("Profilo di piattaforma ripristinato all'uscita da GameMode. Se non "
         "impostato, viene ripristinato il precedente."),
    ),
    _choice(
        "general", "igpu_desiredgov", GOVERNORS, "powersave",
        "; The iGPU desired governor is used when the integrated GPU is under heavy load",
        ("Governor usato per la GPU integrata quando è sotto carico "
         "elevato."),
    ),
    OptionSpec(
        section="general",
        key="igpu_power_threshold",
        type="float",
        default=0.3,
        min_value=-1.0,
        max_value=1.0,
        template="igpu_power_threshold={value}",
        description=("Soglia (rapporto W iGPU / W CPU) oltre cui si considera "
                     "la GPU integrata sotto carico. -1 disabilita il "
                     "controllo."),
        comment=("; Threshold to use to decide when the integrated GPU is "
                 "under heavy load"),
    ),
    _choice(
        "general", "softrealtime", SOFT_REALTIME, "off",
        "; GameMode can change the scheduler policy to SCHED_ISO on kernels which support it",
        ("Politica dello scheduler a tempo reale debole. \"auto\" l'attiva "
         "con 4 o più core, \"on\" sempre, \"off\" mai."),
    ),
    OptionSpec(
        section="general",
        key="renice",
        type="int",
        default=0,
        min_value=0,
        max_value=20,
        template="renice={value}",
        description=("Valore di ``nice`` applicato (negato) ai processi di "
                     "gioco. Richiede l'appartenenza al gruppo ``gamemode``. "
                     "0 = nessuna modifica."),
        comment=("; GameMode can renice game processes. You can put any value "
                 "between 0 and 20 here"),
    ),
    OptionSpec(
        section="general",
        key="ioprio",
        type="choice",
        choices=IOPRIO,
        default="0",
        template="ioprio={value}",
        description=("Priorità I/O applicata ai client. Da 0 (massima) a 7, "
                     "oppure \"off\" (disabilita) o \"reset\" (comportamento "
                     "predefinito)."),
        comment=("; By default, GameMode adjusts the iopriority of clients to "
                 "BE/0"),
    ),
    OptionSpec(
        section="general",
        key="inhibit_screensaver",
        type="bool",
        default=True,
        template="inhibit_screensaver={value}",
        description="Se GameMode deve inibire lo screensaver quando attivo.",
        comment="; Sets whether gamemode will inhibit the screensaver when active",
    ),
    OptionSpec(
        section="general",
        key="disable_splitlock",
        type="bool",
        default=True,
        template="disable_splitlock={value}",
        description="Se GameMode deve disabilitare la mitigazione split lock "
                    "quando attivo.",
        comment="; Sets whether gamemode will disable split lock mitigation when active",
    ),

    # ------------------------------------------------------------------
    # [filter]
    # ------------------------------------------------------------------
    _repeated_list(
        "filter", "whitelist",
        comment=("; If \"whitelist\" entry has a value(s)\n"
                 "; gamemode will reject anything not in the whitelist"),
        description=("Se presente, GameMode accetta solo i programmi elencati "
                     "(il cui nome contiene l'occorrenza)."),
    ),
    _repeated_list(
        "filter", "blacklist",
        comment="; Gamemode will always reject anything in the blacklist",
        description=("GameMode rifiuta sempre i programmi elencati."),
    ),

    # ------------------------------------------------------------------
    # [gpu]  -- unsafe, best-effort hardware tuning
    # ------------------------------------------------------------------
    OptionSpec(
        section="gpu",
        key="apply_gpu_optimisations",
        type="choice",
        choices=["accept-responsibility", "0"],
        default="0",
        template="apply_gpu_optimisations={value}",
        description=("Imposta la chiave \"accept-responsibility\" per "
                     "permettere overclock e ottimizzazioni GPU. NON HA EFFETTO "
                     "se il file è in $PWD o $XDG_CONFIG_HOME."),
        comment=("; Warning: Use these settings at your own risk. Any damage "
                 "to hardware is your responsibility and yours alone"),
        unsafe=True,
    ),
    OptionSpec(
        section="gpu",
        key="gpu_device",
        type="int",
        default=0,
        min_value=0,
        template="gpu_device={value}",
        description=("Numero del dispositivo DRM (di solito 0), cioè il "
                     "numero in /sys/class/drm/card0/."),
        comment="; The DRM device number on the system (usually 0)",
        unsafe=True,
    ),
    OptionSpec(
        section="gpu",
        key="nv_powermizer_mode",
        type="choice",
        choices=["0", "1", "2"],
        default="1",
        template="nv_powermizer_mode={value}",
        description=("GPU PowerMizer Mode NVIDIA. \"Adaptive\"=0, \"Prefer "
                     "Maximum Performance\"=1, \"Auto\"=2. Richiede l'estensione "
                     "coolbits."),
        comment=("; Nvidia specific settings\n"
                 "; Requires the coolbits extension activated in nvidia-xconfig"),
        unsafe=True,
    ),
    OptionSpec(
        section="gpu",
        key="nv_core_clock_mhz_offset",
        type="int",
        default=0,
        template="nv_core_clock_mhz_offset={value}",
        description=("Offset in MHz della frequenza GPU (core). 0 ripristina i "
                     "valori predefiniti, -1 o assente non modifica nulla."),
        unsafe=True,
    ),
    OptionSpec(
        section="gpu",
        key="nv_mem_clock_mhz_offset",
        type="int",
        default=0,
        template="nv_mem_clock_mhz_offset={value}",
        description=("Offset in MHz della frequenza memoria (GPU). 0 "
                     "ripristina i valori predefiniti, -1 o assente non "
                     "modifica nulla."),
        unsafe=True,
    ),
    _choice(
        "gpu", "amd_performance_level", AMD_LEVEL, "high",
        comment=("; AMD specific settings\n"
                 "; Requires a relatively up to date AMDGPU kernel module"),
        description=("Corrisponde a power_dpm_force_performance_level. "
                     "\"manual\" non è supportato al momento."),
        unsafe=True,
    ),
]


# Sections supported by the UI, in the order the steps / output uses them.
SECTIONS_ORDER = ["general", "filter", "gpu"]


def options_for_section(section: str) -> list:
    """Return the :class:`OptionSpec` entries belonging to ``section``."""
    return [opt for opt in OPTIONS if opt.section == section and not opt.standalone]


def section_title(section: str) -> str:
    return {
        "general": "Generale",
        "filter": "Filtro",
        "gpu": "GPU",
    }.get(section, section)