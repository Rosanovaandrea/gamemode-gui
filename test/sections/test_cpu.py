"""Integration tests for the CPU section (``[cpu]``).

Happy path: core pinning (with ranges) and parking, rendered and read back.
Failure paths: invalid core tokens and the options that must stay silent when
they are empty or off.
"""

import _testkit
_testkit.isolate()

from sections.cpu import initializer as cpu_initializer  # noqa: E402
from sections.cpu.core import CpuCore, available_cores  # noqa: E402


def main():
    # --- happy path
    core = CpuCore()
    cpu_initializer.initialize(core, "[cpu]\npin_cores=0-2\npark_cores=1\n", "")
    _testkit.equal("core ranges expanded", core.get_pin_cores(), [0, 1, 2])
    _testkit.equal("parking parsed", core.get_park_cores(), True)
    rendered = core.render_ini_section()
    _testkit.check("cores rendered comma-separated", "pin_cores=0,1,2" in rendered)
    _testkit.check("switch rendered as 1", "park_cores=1" in rendered)

    # --- round-trip
    reloaded = CpuCore()
    cpu_initializer.initialize(reloaded, rendered, "")
    _testkit.equal("round-trip cores", reloaded.get_pin_cores(), [0, 1, 2])
    _testkit.equal("round-trip parking", reloaded.get_park_cores(), True)

    # --- failure paths
    _testkit.equal("empty section renders nothing", CpuCore().render_ini_section(), "")

    silent = CpuCore()
    cpu_initializer.initialize(silent, "[cpu]\npin_cores=\npark_cores=0\n", "")
    _testkit.equal("empty list and off switch are not written",
                   silent.render_ini_section(), "")

    loose = CpuCore()
    cpu_initializer.initialize(loose, "[cpu]\npin_cores=1,x,3-4\n", "")
    _testkit.equal("invalid core tokens skipped", loose.get_pin_cores(), [1, 3, 4])

    # --- special option: the online cores come from the kernel
    _testkit.equal("core choices come from the kernel",
                   core.allowed_values_for(_testkit.option_in(core, "pin_cores")),
                   available_cores())

    _testkit.finish()


if __name__ == "__main__":
    main()
