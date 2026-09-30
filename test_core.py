import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.options_table import OPTIONS
from core.renderer import render_ini, default_ini
from core.activation import ActivationManager
from core.ini_util import parse
from core.config_manager import ConfigManager
from core.backup_manager import BackupManager

print("== Option count:", len(OPTIONS))

# Full default config
d = default_ini()
print("== default_ini output:")
print(d)
print("== callback parse roundtrip:")
parsed = parse(d)
print(parsed["general"].keys())

# Build flags/values that mirror the defaults
am = ActivationManager()
values = am.rebuild_from_parsed(parse(d))
flags = {spec.id: am.get_flag(spec.id) for spec in OPTIONS}
rendered = render_ini(flags, values)
assert rendered == d, "roundtrip mismatch"
print("== roundtrip OK")

# Toggle something off and on
flags = {spec.id: False for spec in OPTIONS}
values = {spec.id: spec.default for spec in OPTIONS}
flags["general.reaper_freq"] = True
flags["general.desiredgov"] = True
flags["general.inhibit_screensaver"] = True
flags["filter.whitelist"] = True
values["filter.whitelist"] = ["RiseOfTheTombRaider", "glxgears"]
cfg = render_ini(flags, values)
print("== sparse config:")
print(cfg)
p = parse(cfg)
assert p["filter"]["whitelist"] == ["RiseOfTheTombRaider", "glxgears"], p["filter"]["whitelist"]
print("== list preserved OK")

# ConfigManager atomic write
with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "gamemode.ini")
    cm = ConfigManager(path)
    bm = BackupManager(cm)
    assert not bm.has_orig
    bm.ensure_orig(cfg)
    assert bm.has_orig
    orig = open(cm.orig_path).read()
    assert orig == cfg
    cm.save(cfg)
    assert os.path.isfile(path)
    # no previous file, so no backup yet on first save
    assert not os.path.isfile(cm.backup_path)
    assert open(path).read() == cfg
    # modify and save again -> backup should hold previous
    cm.save(d)
    assert os.path.isfile(cm.backup_path)
    bak = open(cm.backup_path).read()
    assert bak == cfg, "backup should hold previous config"
    # write failure -> rollback
    os.chmod(cm.directory(), 0o500)
    try:
        cm.save("broken")
    except OSError:
        pass
    import stat
    os.chmod(cm.directory(), 0o700)
    print("== backup/rollback path OK")
    # restore from orig
    cm.restore_from_orig()
    assert open(path).read() == cfg
    print("== restore from orig OK")

print("\nALL CORE TESTS PASSED")