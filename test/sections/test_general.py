"""Integration tests for the General section (``[general]``).

Happy path: load the section from the base/override texts, read it back and
render it. Failure paths: unparsable values, comments and the ``:`` separator,
override precedence, the saved-session fallback and the kernel-derived governors.
"""

import _testkit
_testkit.isolate()

from sections.general import initializer as general_initializer  # noqa: E402
from sections.general.core import GeneralCore, available_governors  # noqa: E402

BASE_TEXT = "[general]\nreaper_freq=3\nrenice=5\n"
OVERRIDE_TEXT = "[general]\n; the user override\nreaper_freq=9\nsoftrealtime=on\n"


def main():
    # --- happy path: the override wins, base values survive, only non-defaults render
    core = GeneralCore()
    general_initializer.initialize(core, BASE_TEXT, OVERRIDE_TEXT)
    _testkit.equal("override wins over the base", core.get_reaper_freq(), 9)
    _testkit.equal("base value kept when not overridden", core.get_renice(), 5)
    _testkit.equal("string choice parsed", core.get_softrealtime(), "on")

    rendered = core.render_ini_section()
    _testkit.check("section header present", rendered.startswith("[general]\n"))
    _testkit.check("active value rendered", "reaper_freq=9" in rendered)
    _testkit.check("defaults are not written",
                   "inhibit_screensaver" not in rendered and "ioprio" not in rendered)

    # --- round-trip: what we render, we can read back
    reloaded = GeneralCore()
    general_initializer.initialize(reloaded, rendered, "")
    _testkit.equal("round-trip reaper_freq", reloaded.get_reaper_freq(), 9)
    _testkit.equal("round-trip renice", reloaded.get_renice(), 5)
    _testkit.equal("round-trip softrealtime", reloaded.get_softrealtime(), "on")

    # --- failure paths
    broken = GeneralCore()
    general_initializer.initialize(
        broken, "[general]\nreaper_freq=not-a-number\nigpu_power_threshold=x\n", "")
    _testkit.equal("invalid int keeps the default", broken.get_reaper_freq(), 5)
    _testkit.equal("invalid float keeps the default", broken.get_igpu_power_threshold(), 0.3)

    variants = GeneralCore()
    general_initializer.initialize(
        variants, "[general]\ninhibit_screensaver: 0\nrenice = 7 ; note\n", "")
    _testkit.equal("'0' is parsed as false", variants.get_inhibit_screensaver(), False)
    _testkit.equal("trailing comment stripped", variants.get_renice(), 7)

    # The saved session is only a fallback: it must not override the files.
    fallback = GeneralCore()
    general_initializer.initialize(fallback, "", "", {"general.reaper_freq": 42})
    _testkit.equal("session used when no text has the section", fallback.get_reaper_freq(), 42)
    present = GeneralCore()
    general_initializer.initialize(present, "[general]\nreaper_freq=2\n", "",
                                   {"general.reaper_freq": 42})
    _testkit.equal("session ignored when a text has the section", present.get_reaper_freq(), 2)

    # --- special option: the governors come from the kernel, the rest is static
    _testkit.equal("governor choices come from the kernel",
                   core.allowed_values_for(_testkit.option_in(core, "desiredgov")),
                   available_governors())
    _testkit.equal("static choices",
                   core.allowed_values_for(_testkit.option_in(core, "softrealtime")),
                   ["auto", "on", "off"])

    # --- an empty section renders nothing (no header)
    _testkit.equal("empty section renders nothing", GeneralCore().render_ini_section(), "")

    _testkit.finish()


if __name__ == "__main__":
    main()
