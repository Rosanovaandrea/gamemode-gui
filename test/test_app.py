"""Application tests (no GUI): bootstrap, state, save, restore, reload.

Exercises the general initializer (which wires the sections) and the general core
(orchestration + atomic save / restore / factory reset) through the public API.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolation: never touch the real user settings or the real /etc configuration.
_WORK = tempfile.mkdtemp(prefix="gamemodegui_app_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_WORK, "config")
os.environ["GAMEMODE_CONFIG"] = os.path.join(_WORK, "etc", "gamemode.ini")
os.environ["GAMEMODE_BASE"] = os.path.join(_WORK, "usr-share", "gamemode", "gamemode.ini")
os.makedirs(os.path.dirname(os.environ["GAMEMODE_CONFIG"]), exist_ok=True)
os.makedirs(os.path.dirname(os.environ["GAMEMODE_BASE"]), exist_ok=True)

import initializer  # noqa: E402
from sections.general.core import GeneralCore  # noqa: E402

# A package-installed "base" file, as a distribution would ship it.
BASE_TEXT = "[general]\n; base comment\nreaper_freq=3\n[custom]\nstart=base1\n"
with open(os.environ["GAMEMODE_BASE"], "w", encoding="utf-8") as handle:
    handle.write(BASE_TEXT)

app = initializer.build_app()
general = next(section for section in app.core.sections if section.section_id == "general")
custom = next(section for section in app.core.sections if section.section_id == "custom")
assert isinstance(general, GeneralCore)

# The sections loaded their own slice from the installed base.
assert general.get_reaper_freq() == 3
assert custom.get_start() == ["base1"]

# A speaking setter updates the section state.
general.set_reaper_freq(10)
assert general.get_reaper_freq() == 10
assert app.core.store.is_dirty()

# The general core orchestrates the sections' own output.
content = app.core.render()
assert "reaper_freq=10" in content and "start=base1" in content

# First save: atomic commit + pristine `.orig` baseline, no previous state yet.
app.core.save()
path = app.config_path
assert os.path.isfile(path)
assert not app.core.store.is_dirty()
assert open(path, encoding="utf-8").read() == content
assert open(path + ".orig", encoding="utf-8").read() == ""  # no active file to preserve
assert not os.path.isfile(path + ".bak")

# Second save: a backup of the previous state now exists.
general.set_reaper_freq(7)
app.core.save()
assert os.path.isfile(path + ".bak")
assert "reaper_freq=10" in open(path + ".bak", encoding="utf-8").read()

# A value absent from the restored file must revert to its default, because a
# reload resets every section before applying the file.
general.set_renice(15)
assert general.get_renice() == 15

# Restore the previous state and reload the sections from disk.
assert app.core.restore_previous()
initializer.reload(app)
assert general.get_reaper_freq() == 10
assert general.get_renice() == 0

# Factory reset restores the pristine `.orig` baseline.
assert app.core.restore_factory()
initializer.reload(app)
assert general.get_reaper_freq() == 3
assert custom.get_start() == ["base1"]

print("ALL APP TESTS PASSED")
