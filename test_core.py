"""Test della logica (senza GUI): tabella, renderer, attivazione,
config manager (commit atomico locale + privilegiato), i18n e sessione."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core
from core import (
    ActivationManager, ConfigManager, OPTIONS, OptionSpec,
    default_ini, parse_ini, render_ini, tr,
)
from core import save_session, load_session

print("== Opzioni in tabella:", len(OPTIONS))
assert "general" in core.SECTIONS_ORDER

# ---------------------------------------------------------------------------
# 1. Renderer: roundtrip tabella -> file -> tabella
# ---------------------------------------------------------------------------
d = default_ini()
print("== default_ini:\n", d)
parsed = parse_ini(d)
am = ActivationManager()
values = am.rebuild_from_parsed(parsed)
flags = {spec.id: am.get_flag(spec.id) for spec in OPTIONS}
rendered = render_ini(flags, values)
assert rendered == d, "roundtrip mismatch"
print("== roundtrip OK")

# ---------------------------------------------------------------------------
# 2. Liste (whitelist/blacklist) come chiavi ripetute
# ---------------------------------------------------------------------------
flags2 = {spec.id: False for spec in OPTIONS}
values2 = {spec.id: spec.default for spec in OPTIONS}
flags2["filter.whitelist"] = True
values2["filter.whitelist"] = ["RiseOfTheTombRaider", "glxgears"]
cfg = render_ini(flags2, values2)
p2 = parse_ini(cfg)
assert p2["filter"]["whitelist"] == ["RiseOfTheTombRaider", "glxgears"]
print("== liste ripetute OK")

# ---------------------------------------------------------------------------
# 3. ConfigManager: commit locale atomico + .orig + .bak + rollback
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
# 4. i18n via XML (it) — configurabile, non hardcoded
# ---------------------------------------------------------------------------
assert tr("window.title") == "GameMode GUI"
assert tr("btn.save") == "Salva"
assert tr("chiave.inesistente") == "chiave.inesistente"  # fallback sul key
print("== i18n OK")

# ---------------------------------------------------------------------------
# 5. Sessione (persistenza delle scelte su file JSON)
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "gamemode.ini")
    flags_s = {"general.reaper_freq": True, "general.desiredgov": True}
    values_s = {"general.reaper_freq": 7, "general.desiredgov": "powersave"}
    save_session(path, flags_s, values_s)
    restored = load_session(path)
    assert restored is not None
    f2, v2 = restored
    assert f2["general.reaper_freq"] is True
    assert v2["general.reaper_freq"] == 7
    assert v2["general.desiredgov"] == "powersave"
print("== sessione OK")

# ---------------------------------------------------------------------------
# 6. Privileged helper (simulazione locale, senza root)
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

print("\nALL CORE TESTS PASSED")