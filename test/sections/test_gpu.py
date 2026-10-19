"""Integration tests for the GPU section (``[gpu]``).

Happy path: load the master switch and a device, render and read back. Failure
paths: an invalid integer, and the classic trap where the dependent options must
be ignored while the master switch is off.
"""

import _testkit
_testkit.isolate()

from sections.gpu.core import GpuCore  # noqa: E402

MASTER = "apply_gpu_optimisations"


def main():
    # --- happy path
    core = GpuCore()
    core.load_texts("[gpu]\napply_gpu_optimisations=accept-responsibility\ngpu_device=1\n", "")
    _testkit.equal("master switch parsed", core.get_apply_gpu_optimisations(),
                   "accept-responsibility")
    _testkit.equal("device parsed", core.get_gpu_device(), 1)
    rendered = core.render_ini_section()
    _testkit.check("master rendered",
                   "apply_gpu_optimisations=accept-responsibility" in rendered)
    _testkit.check("device rendered", "gpu_device=1" in rendered)

    # --- the trap: dependent options are ignored while the master switch is off
    off = GpuCore()
    off.set_gpu_device(2)                       # a sub option set while master is off
    _testkit.equal("master off writes no [gpu] block", off.render_ini_section(), "")
    _testkit.check("master switch reports inactive by default",
                   not off.is_option_active(_testkit.option_in(off, MASTER)))
    off.set_apply_gpu_optimisations("accept-responsibility")
    _testkit.check("master switch reports active once on",
                   off.is_option_active(_testkit.option_in(off, MASTER)))
    _testkit.check("dependent option rendered once master is on",
                   "gpu_device=2" in off.render_ini_section())

    # A file that sets the subs but leaves the master off must write nothing.
    off_file = GpuCore()
    off_file.load_texts("[gpu]\ngpu_device=3\n", "")
    _testkit.equal("subs set while master is off are not written",
                   off_file.render_ini_section(), "")

    # --- invalid integer keeps the default
    broken = GpuCore()
    broken.load_texts("[gpu]\ngpu_device=not-a-number\n", "")
    _testkit.equal("invalid int keeps the default", broken.get_gpu_device(), 0)

    # --- unchanged dependent options are not written, even with the master on
    master_only = GpuCore()
    master_only.set_apply_gpu_optimisations("accept-responsibility")
    text = master_only.render_ini_section()
    _testkit.check("unchanged dependent options not written",
                   "gpu_device" not in text and "nv_powermizer_mode" not in text)

    _testkit.finish()


if __name__ == "__main__":
    main()
