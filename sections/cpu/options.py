"""Options of the CPU section (the ``[cpu]`` keys).

The option descriptors are the single source of truth for the ``[cpu]`` block.
They live here, apart from the core, so they are easy to find and edit; the core
imports them and owns the state, the rendering and the parsing.
"""

from __future__ import annotations

from typing import List

from spec import OptionSpec

CPU_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="pin_cores", type="cores", default=[],
        special=True, special_source="cpu_cores",
        description_id="opt.cpu.pin_cores",
        comment="; Pin the game to a specific list of cores (comma separated, "
                "\"-\" for ranges).\n; Leave empty to let GameMode auto-detect the "
                "cores to use."),
    OptionSpec(
        key="park_cores", type="bool", default=False,
        description_id="opt.cpu.park_cores",
        comment="; Park (offline) all cores except the ones used by the game.\n"
                "; Requires the user to be in the 'gamemode' group."),
]
