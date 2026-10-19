"""Engine tests (no GUI): each section's options + INI (de)serialisation, i18n.

Every section is self-contained, so these tests exercise each section core on its
own: it defines its options, renders only its active ones and reads itself back.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolation: the language preference must not read the real config.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="gamemodegui_engine_")

import i18n.settings as i18n_settings  # noqa: E402
from sections.cpu.core import CpuCore, available_cores, expand_cpu_list  # noqa: E402
from sections.custom.core import CustomCore  # noqa: E402
from sections.general.core import GeneralCore, available_governors  # noqa: E402
from sections.general.options import GENERAL_OPTIONS  # noqa: E402
from sections.gpu.core import GpuCore  # noqa: E402

# ---------------------------------------------------------------------------
# General: render only active options + roundtrip + kernel governors
# ---------------------------------------------------------------------------
general = GeneralCore()
assert general.render_ini_section() == ""
assert general.get_reaper_freq() == 5
assert general.get_desiredgov() == "performance"
assert available_governors()
governor_option = next(spec for spec in GENERAL_OPTIONS if spec.key == "desiredgov")
assert general.allowed_values_for(governor_option) == available_governors()
softrealtime_option = next(spec for spec in GENERAL_OPTIONS if spec.key == "softrealtime")
assert general.allowed_values_for(softrealtime_option) == ["auto", "on", "off"]

general.set_reaper_freq(10)
general.set_inhibit_screensaver(False)
general.set_desiredgov("powersave")
general_text = general.render_ini_section()
assert "reaper_freq=10" in general_text
assert "inhibit_screensaver=0" in general_text
assert "desiredgov=powersave" in general_text
assert "renice" not in general_text and "disable_splitlock" not in general_text

reloaded = GeneralCore()
reloaded.apply_parsed_section({"reaper_freq": ["10"], "inhibit_screensaver": ["0"],
                               "desiredgov": ["powersave"]})
assert reloaded.render_ini_section() == general_text
print("== general core OK")

# ---------------------------------------------------------------------------
# GPU: dependent options are written only when the master switch is on
# ---------------------------------------------------------------------------
gpu = GpuCore()
assert gpu.render_ini_section() == ""
gpu.set_gpu_device(2)
assert gpu.render_ini_section() == ""                       # master off -> nothing written
gpu.set_apply_gpu_optimisations("accept-responsibility")
assert gpu.is_option_active(gpu.options[0])
gpu_text = gpu.render_ini_section()
assert "apply_gpu_optimisations=accept-responsibility" in gpu_text
assert "gpu_device=2" in gpu_text
print("== gpu core OK")

# ---------------------------------------------------------------------------
# CPU: core pinning (kernel cores) + parking
# ---------------------------------------------------------------------------
assert expand_cpu_list("0-3,8") == [0, 1, 2, 3, 8]
assert available_cores() and all(core.isdigit() for core in available_cores())
cpu = CpuCore()
cpu.set_pin_cores([0, 2, 4])
cpu.set_park_cores(True)
cpu_text = cpu.render_ini_section()
assert "pin_cores=0,2,4" in cpu_text and "park_cores=1" in cpu_text
cpu_reloaded = CpuCore()
cpu_reloaded.apply_parsed_section({"pin_cores": ["0-2"], "park_cores": ["1"]})
assert cpu_reloaded.get_pin_cores() == [0, 1, 2]
assert cpu_reloaded.get_park_cores() is True
print("== cpu core OK")

# ---------------------------------------------------------------------------
# Custom: script lists (repeated keys) + notification toggles + append
# ---------------------------------------------------------------------------
custom = CustomCore()
assert custom.render_ini_section() == ""
custom.set_start(["notify-send hi", "echo bye"])
custom.set_end(["cleanup.sh"])
custom.set_script_timeout(20)
custom_text = custom.render_ini_section()
assert "start=notify-send hi" in custom_text and "start=echo bye" in custom_text
assert "end=cleanup.sh" in custom_text and "script_timeout=20" in custom_text

custom.set_notify_start(True)
custom_text = custom.render_ini_section()
assert 'start=notify-send "GameMode started"' in custom_text
assert (custom_text.index('start=notify-send "GameMode started"')
        < custom_text.index("start=notify-send hi"))

merged = CustomCore()
merged.apply_parsed_section({"start": ["base1"]})
merged.apply_parsed_section({"start": ["over1"]}, append=True)
assert merged.get_start() == ["base1", "over1"]

extracted = CustomCore()
extracted.apply_parsed_section({"start": ['notify-send "GameMode started"', "echo x"]})
assert extracted.get_notify_start() is True
assert extracted.get_start() == ["echo x"]
print("== custom core OK")

# ---------------------------------------------------------------------------
# i18n: translations, normalisation, detection and preference
# ---------------------------------------------------------------------------
from i18n.translator import Translator  # noqa: E402

assert Translator("it").tr("window.title") == "GameMode GUI"
assert Translator("it").tr("btn.save") == "Salva"
assert Translator("en").tr("btn.save") == "Save"
assert Translator("it").tr("key.missing") == "key.missing"

assert i18n_settings.supported_lang("it_IT.UTF-8") == "it"
assert i18n_settings.supported_lang("en-US") == "en"
assert i18n_settings.supported_lang("fr_FR.UTF-8") is None

os.environ["LC_ALL"] = "it_IT.UTF-8"
assert i18n_settings.detect_system_lang() == "it"
os.environ["LC_ALL"] = "fr_FR.UTF-8"
assert i18n_settings.detect_system_lang() == "en"
del os.environ["LC_ALL"]

with tempfile.TemporaryDirectory() as work:
    os.environ["XDG_CONFIG_HOME"] = work
    i18n_settings.reset_supported_langs()
    os.environ["LC_ALL"] = "it_IT.UTF-8"
    assert i18n_settings.resolve_lang() == "it"
    i18n_settings.save_lang("en")
    assert i18n_settings.load_saved_lang() == "en"
    assert i18n_settings.resolve_lang() == "en"          # the saved choice wins
    i18n_settings.save_lang("fr")                        # unsupported -> English
    assert i18n_settings.load_saved_lang() == "en"
    del os.environ["LC_ALL"]
print("== i18n OK")

# ---------------------------------------------------------------------------
# Privileged helper (local simulation, without root)
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as work:
    path = os.path.join(work, "gamemode.ini")
    helper = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services", "privileged_helper.py")
    process = subprocess.run([sys.executable, helper, "commit", path],
                             input=general_text, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert open(path, encoding="utf-8").read() == general_text
    assert os.path.isfile(path + ".orig")
print("== privileged helper commit OK")

print("\nALL ENGINE TESTS PASSED")
