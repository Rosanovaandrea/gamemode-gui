"""Test della logica (senza GUI): tabella, renderer, attivazione,
config manager (commit atomico locale + privilegiato), i18n e sessione."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Isolamento: le impostazioni (lingua) non devono leggere la config reale.
_CFG_TMP = tempfile.mkdtemp(prefix="gamemodegui_core_")
os.environ["XDG_CONFIG_HOME"] = _CFG_TMP

import core
from core import (
    ConfigManager, OPTIONS, OptionSpec,
    default_ini, default_values, parse_ini, render_ini,
    values_from_parsed,
)
from core import save_session, load_session

print("== Opzioni in tabella:", len(OPTIONS))
assert "general" in core.SECTIONS_ORDER

# ---------------------------------------------------------------------------
# 0. Definizioni caricate da options.json (data-driven)
# ---------------------------------------------------------------------------
assert [c.id for c in core.CATEGORIES] == ["general", "gpu", "cpu", "custom"]
assert len(OPTIONS) == 25
for spec in OPTIONS:
    assert spec.description_id and spec.type and spec.widget, spec.id
    assert core.OPTIONS_BY_ID[spec.id] is spec

# Valori "speciali" letti dal sistema (governor CPU).
gov_spec = core.OPTIONS_BY_ID["general.desiredgov"]
assert gov_spec.special and gov_spec.special_source == "cpu_governors"
govs = core.get_cpu_governors()
assert govs, "lista governor vuota"
assert core.resolve_choices(gov_spec) == govs
# Valori normali: scelte statiche dal JSON.
assert core.resolve_choices(core.OPTIONS_BY_ID["general.softrealtime"]) == ["auto", "on", "off"]

# ioprio: scelta a pulsanti con valori speciali "off" e "reset".
ioprio = core.OPTIONS_BY_ID["general.ioprio"]
ioprio_choices = core.resolve_choices(ioprio)
assert ioprio.type == "choice" and ioprio.widget == "radio"
assert "off" in ioprio_choices and "reset" in ioprio_choices

# CPU: pinning speciale (core dal sistema) + parking bool.
pin = core.OPTIONS_BY_ID["cpu.pin_cores"]
assert pin.type == "cores" and pin.special and pin.special_source == "cpu_cores"
cores = core.get_cpu_cores()
assert cores and all(c.isdigit() for c in cores)
assert core.resolve_choices(pin) == cores
assert core.OPTIONS_BY_ID["cpu.park_cores"].type == "bool"

# Custom: start/end liste + timeout int.
assert core.OPTIONS_BY_ID["custom.start"].type == "list"
assert core.OPTIONS_BY_ID["custom.end"].type == "list"
assert core.OPTIONS_BY_ID["custom.script_timeout"].default == 10
print("== options.json caricato OK (governor:", ", ".join(govs), "| core:", ",".join(cores), ")")

# ---------------------------------------------------------------------------
# 1. Renderer: solo opzioni attive (default NON scritti) + roundtrip
# ---------------------------------------------------------------------------
# Un file con tutti i default equivale a nessuna chiave.
assert default_ini() == ""
print("== default_ini() vuoto (nessun default scritto)")

values = default_values()
values["general.reaper_freq"] = 10
values["general.inhibit_screensaver"] = False
d = render_ini(values)
print("== render (solo attive):\n", d)
assert "reaper_freq=10" in d
assert "inhibit_screensaver=0" in d
# I default non toccati non compaiono.
assert "renice" not in d
assert "disable_splitlock" not in d
parsed = parse_ini(d)
values_round = values_from_parsed(parsed)
rendered = render_ini(values_round)
assert rendered == d, "roundtrip mismatch"
print("== roundtrip OK")

# ---------------------------------------------------------------------------
# 2. [gpu]: le opt dipendenti esistono solo con apply_gpu_optimisations attivo
# ---------------------------------------------------------------------------
gpu_values = default_values()
gpu_values["gpu.gpu_device"] = 1          # dipende dall'interruttore, spento
gpu_values["gpu.nv_core_clock_mhz_offset"] = 150
gpu_off = render_ini(gpu_values)
assert gpu_off == "", f"gpu scritte senza interruttore: {gpu_off!r}"

gpu_values["gpu.apply_gpu_optimisations"] = "accept-responsibility"
gpu_on = render_ini(gpu_values)
assert "apply_gpu_optimisations=accept-responsibility" in gpu_on
assert "gpu_device=1" in gpu_on
assert "nv_core_clock_mhz_offset=150" in gpu_on
print("== dipendenza [gpu] OK")

# ---------------------------------------------------------------------------
# 3b. CPU (pinning cores + parking) e script custom (liste ripetute)
# ---------------------------------------------------------------------------
cv = default_values()
cv["cpu.pin_cores"] = [0, 2, 4]
cv["cpu.park_cores"] = True
r_cpu = render_ini(cv)
assert "pin_cores=0,2,4" in r_cpu
assert "park_cores=1" in r_cpu
pv = values_from_parsed(parse_ini(r_cpu))
assert pv["cpu.pin_cores"] == [0, 2, 4]
assert pv["cpu.park_cores"] is True

cv2 = default_values()
cv2["custom.start"] = ["notify-send hi", "echo bye"]
cv2["custom.end"] = ["cleanup.sh"]
cv2["custom.script_timeout"] = 20
r_custom = render_ini(cv2)
assert "start=notify-send hi" in r_custom and "start=echo bye" in r_custom
assert "end=cleanup.sh" in r_custom
assert "script_timeout=20" in r_custom
p_custom = parse_ini(r_custom)
assert p_custom["custom"]["start"] == ["notify-send hi", "echo bye"]
print("== cpu pinning/parking + custom scripts OK")

# ---------------------------------------------------------------------------
# 3d. Toggle notifiche (value_type "toggle_entry") nella sezione custom
# ---------------------------------------------------------------------------
notify_start = core.OPTIONS_BY_ID["custom.notify_start"]
assert notify_start.type == "toggle_entry"
assert notify_start.target == "custom.start"
assert notify_start.entry == 'notify-send "GameMode started"'
assert core.OPTIONS_BY_ID["custom.notify_end"].target == "custom.end"

nv = default_values()
assert nv["custom.notify_start"] is False and nv["custom.notify_end"] is False
assert "notify-send" not in render_ini(nv)      # spenti -> nessuna riga

nv["custom.notify_start"] = True
nv["custom.start"] = ["/home/andrea/gamemode_Start.sh"]
nv["custom.notify_end"] = True
nv["custom.end"] = ["/home/andrea/gamemode_Stop.sh"]
r_nv = render_ini(nv)
assert 'start=notify-send "GameMode started"' in r_nv
assert 'end=notify-send "GameMode ended"' in r_nv
# La notifica viene scritta PRIMA degli altri script (come nel template).
assert (r_nv.index('start=notify-send "GameMode started"')
        < r_nv.index("start=/home/andrea/gamemode_Start.sh"))
assert (r_nv.index('end=notify-send "GameMode ended"')
        < r_nv.index("end=/home/andrea/gamemode_Stop.sh"))

# Round-trip: leggendo il file la notifica accende il toggle e sparisce dalla
# lista (è gestita solo dall'interruttore); ricomponendo si ha lo stesso file.
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "gamemode.ini")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(r_nv)
    loaded = core.load_values_from_file(p)
    assert loaded["custom.notify_start"] is True
    assert loaded["custom.notify_end"] is True
    assert loaded["custom.start"] == ["/home/andrea/gamemode_Start.sh"]
    assert loaded["custom.end"] == ["/home/andrea/gamemode_Stop.sh"]
    assert render_ini(loaded) == r_nv
print("== toggle notifiche custom OK")

# ---------------------------------------------------------------------------
# 3c. Base installata + override /etc (merge come il daemon) + commenti
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    base = os.path.join(td, "usr-share", "gamemode", "gamemode.ini")
    over = os.path.join(td, "etc", "gamemode.ini")
    os.makedirs(os.path.dirname(base))
    os.makedirs(os.path.dirname(over))
    with open(base, "w", encoding="utf-8") as fh:
        fh.write("[general]\n; commento base\nreaper_freq=3\n[custom]\nstart=base1\n")
    with open(over, "w", encoding="utf-8") as fh:
        fh.write("[general]\nreaper_freq=7\n[custom]\nstart=over1\n")

    merged = core.load_effective_values(base, over)
    assert merged["general.reaper_freq"] == 7                 # override vince
    assert merged["custom.start"] == ["base1", "over1"]       # liste accodate

    comments = core.load_base_comments(base)
    assert comments["general.reaper_freq"].startswith(";")
    r = core.render_ini(merged, comments)
    assert "reaper_freq=7" in r and "; commento base" in r

    os.environ["GAMEMODE_BASE"] = base
    assert core.resolve_base_path() == base
    del os.environ["GAMEMODE_BASE"]
print("== base installata + override + commenti OK")

# ---------------------------------------------------------------------------
# 3. Liste (script custom) come chiavi ripetute
# ---------------------------------------------------------------------------
values2 = default_values()
values2["custom.start"] = ["notify-send start", "echo go"]
cfg = render_ini(values2)
p2 = parse_ini(cfg)
assert p2["custom"]["start"] == ["notify-send start", "echo go"]
print("== liste ripetute OK")

# ---------------------------------------------------------------------------
# 4. ConfigManager: commit locale atomico + .orig + .bak + rollback
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "gamemode.ini")
    cm = ConfigManager(path)
    cm.save(cfg)                                   # primo commit
    assert os.path.isfile(path)
    assert os.path.isfile(cm.orig_path)            # .orig creato una volta
    assert open(path).read() == cfg
    assert not os.path.isfile(cm.backup_path)      # nessun precedente -> no .bak

    cm.save(d)                                     # secondo commit
    assert os.path.isfile(cm.backup_path)          # ora .bak esiste
    assert open(cm.backup_path).read() == cfg      # .bak == stato precedente

    # rollback dal backup
    assert cm.rollback_from_backup()
    assert open(path).read() == cfg

    # ripristino da orig
    assert cm.restore_from_orig()
    print("== commit locale + .orig + .bak + rollback OK")

# ---------------------------------------------------------------------------
# 5. i18n via XML (it/en) — selezione, normalizzazione e fallback
# ---------------------------------------------------------------------------
from core import Translator

assert Translator("it").tr("window.title") == "GameMode GUI"
assert Translator("it").tr("btn.save") == "Salva"
assert Translator("en").tr("btn.save") == "Save"
assert Translator("it").tr("chiave.inesistente") == "chiave.inesistente"  # fallback sul key

# Normalizzazione dei codici lingua (accetta it_IT.UTF-8, en-US, ...).
assert core.supported_lang("it_IT.UTF-8") == "it"
assert core.supported_lang("en-US") == "en"
assert core.supported_lang("fr_FR.UTF-8") is None
assert core.supported_lang("C") is None
assert core.supported_lang("") is None

# Rilevamento dal locale di sistema: vince la prima variabile impostata;
# se non è it/en si usa l'inglese.
os.environ["LC_ALL"] = "it_IT.UTF-8"
assert core.detect_system_lang() == "it"
os.environ["LC_ALL"] = "fr_FR.UTF-8"
assert core.detect_system_lang() == "en"
del os.environ["LC_ALL"]

# La preferenza salvata dall'utente ha la precedenza su tutto (anche sul locale).
with tempfile.TemporaryDirectory() as td:
    os.environ["XDG_CONFIG_HOME"] = td
    os.environ["LC_ALL"] = "it_IT.UTF-8"
    assert core.resolve_lang() == "it"
    assert core.settings_path().startswith(td)
    core.save_lang("en")
    assert core.load_saved_lang() == "en"
    assert core.resolve_lang() == "en"       # la scelta salvata vince
    core.save_lang("fr")                     # non supportata -> inglese
    assert core.load_saved_lang() == "en"
    del os.environ["LC_ALL"]

# Elenco lingue letto dalla configurazione + validazione sui file.
with tempfile.TemporaryDirectory() as td:
    os.environ["XDG_CONFIG_HOME"] = td

    # Default (nessun settings.json): italiano + inglese.
    core.reset_supported_langs()
    assert core.supported_langs() == ("it", "en")
    assert core.available_langs() == [("it", "Italiano"), ("en", "English")]
    assert core.lang_label("it") == "Italiano"
    assert core.lang_label("zz") == "ZZ"      # nessun file/attributo -> codice

    # Lista valida con una lingua senza file -> scartata e segnalata.
    core.save_settings({"supported_langs": ["it", "en", "de"]})
    core.reset_supported_langs()
    assert core.supported_langs() == ("it", "en")
    assert any("de" in m for m in core.describe_lang_errors())

    # Lista fatta solo di lingue senza file -> fallback ai default + errore.
    core.save_settings({"supported_langs": ["de", "fr"]})
    core.reset_supported_langs()
    assert core.supported_langs() == ("it", "en")
    assert core.describe_lang_errors()

    # Tipo sbagliato per supported_langs -> fallback + errore.
    core.save_settings({"supported_langs": "it"})
    core.reset_supported_langs()
    assert core.supported_langs() == ("it", "en")
    assert core.describe_lang_errors()

    # Voci non stringa -> ignorate e segnalate.
    core.save_settings({"supported_langs": [123, "it"]})
    core.reset_supported_langs()
    assert core.supported_langs() == ("it",)
    assert any("123" in m for m in core.describe_lang_errors())

    # settings.json rotto -> fallback ai default + errore.
    with open(core.settings_path(), "w", encoding="utf-8") as fh:
        fh.write("{non-json")
    core.reset_supported_langs()
    assert core.supported_langs() == ("it", "en")
    assert core.describe_lang_errors()
print("== i18n OK")

# ---------------------------------------------------------------------------
# 6. Sessione (persistenza dei valori su file JSON)
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "gamemode.ini")
    values_s = {"general.reaper_freq": 7, "general.desiredgov": "powersave"}
    save_session(path, values_s)
    restored = load_session(path)
    assert restored is not None
    assert restored["general.reaper_freq"] == 7
    assert restored["general.desiredgov"] == "powersave"
print("== sessione OK")

# ---------------------------------------------------------------------------
# 7. Privileged helper (simulazione locale, senza root)
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "gamemode.ini")
    # execute privileged.py as a subprocess (non-root -> funziona come root locale)
    import subprocess
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privileged.py")
    proc = subprocess.run([sys.executable, helper, "commit", path],
                          input=cfg, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert open(path).read() == cfg
    assert os.path.isfile(path + ".orig")
    print("== privileged.py commit OK")

    # Seed del .orig dal file installato (commit con seed path)
    path2 = os.path.join(td, "gamemode2.ini")
    seed = os.path.join(td, "seed.ini")
    with open(seed, "w", encoding="utf-8") as fh:
        fh.write("; seed installato\n")
    proc = subprocess.run([sys.executable, helper, "commit", path2, seed],
                          input=cfg, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert open(path2 + ".orig").read() == "; seed installato\n"
    print("== privileged.py seed .orig OK")

print("\nALL CORE TESTS PASSED")