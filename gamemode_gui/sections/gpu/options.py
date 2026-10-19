"""Options of the GPU section (the ``[gpu]`` keys).

The option descriptors are the single source of truth for the ``[gpu]`` block.
They live here, apart from the core, so they are easy to find and edit; the core
imports them and owns the state, the rendering and the parsing.
"""

from __future__ import annotations

from typing import List

from gamemode_gui.spec import OptionSpec

GPU_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="apply_gpu_optimisations", type="enable", default="0",
        on_value="accept-responsibility", label_id="opt.gpu.enable_power_plan.label",
        description_id="opt.gpu.apply_gpu_optimisations",
        comment="; Warning: Use these settings at your own risk. Any damage to "
                "hardware is your responsibility and yours alone"),
    OptionSpec(
        key="gpu_device", type="int", default=0, min_value=0,
        description_id="opt.gpu.gpu_device", depends_on="apply_gpu_optimisations",
        comment="; The DRM device number on the system (usually 0)"),
    OptionSpec(
        key="nv_powermizer_mode", type="choice", default="", choices=["0", "1", "2"],
        description_id="opt.gpu.nv_powermizer_mode",
        depends_on="apply_gpu_optimisations",
        comment="; Nvidia specific settings\n; Requires the coolbits extension "
                "activated in nvidia-xconfig"),
    OptionSpec(
        key="nv_core_clock_mhz_offset", type="int", default=-1,
        description_id="opt.gpu.nv_core_clock_mhz_offset",
        depends_on="apply_gpu_optimisations"),
    OptionSpec(
        key="nv_mem_clock_mhz_offset", type="int", default=-1,
        description_id="opt.gpu.nv_mem_clock_mhz_offset",
        depends_on="apply_gpu_optimisations"),
    OptionSpec(
        key="amd_performance_level", type="choice", default="",
        choices=["auto", "low", "high", "manual"],
        description_id="opt.gpu.amd_performance_level",
        depends_on="apply_gpu_optimisations",
        comment="; AMD specific settings\n; Requires a relatively up to date "
                "AMDGPU kernel module"),
]
