"""Options of the General section (the ``[general]`` keys).

The option descriptors are the single source of truth for the ``[general]``
block. They live here, apart from the core, so they are easy to find and edit;
the core imports them and owns the state, the rendering and the parsing.
"""

from __future__ import annotations

from typing import List

from spec import OptionSpec

GENERAL_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="reaper_freq", type="int", default=5, min_value=1,
        description_id="opt.general.reaper_freq",
        comment="; The reaper thread will check every 5 seconds for exited clients, "
                "for config file changes, and for the CPU/iGPU power balance"),
    OptionSpec(
        key="desiredgov", type="choice", default="performance",
        special=True, special_source="cpu_governors",
        description_id="opt.general.desiredgov",
        comment="; The desired governor is used when entering GameMode instead "
                "of \"performance\""),
    OptionSpec(
        key="defaultgov", type="choice", default="",
        special=True, special_source="cpu_governors",
        description_id="opt.general.defaultgov",
        comment="; The default governor is used when leaving GameMode instead of "
                "restoring the original value"),
    OptionSpec(
        key="igpu_desiredgov", type="choice", default="powersave",
        special=True, special_source="cpu_governors",
        description_id="opt.general.igpu_desiredgov",
        comment="; The iGPU desired governor is used when the integrated GPU is "
                "under heavy load"),
    OptionSpec(
        key="igpu_power_threshold", type="float", default=0.3,
        min_value=-1.0, max_value=1.0,
        description_id="opt.general.igpu_power_threshold",
        comment="; Threshold to use to decide when the integrated GPU is under "
                "heavy load"),
    OptionSpec(
        key="softrealtime", type="choice", default="off",
        choices=["auto", "on", "off"],
        description_id="opt.general.softrealtime",
        comment="; GameMode can change the scheduler policy to SCHED_ISO on "
                "kernels which support it"),
    OptionSpec(
        key="renice", type="int", default=0, min_value=0, max_value=20,
        description_id="opt.general.renice",
        comment="; GameMode can renice game processes. You can put any value "
                "between 0 and 20 here"),
    OptionSpec(
        key="ioprio", type="choice", default="0",
        choices=["0", "1", "2", "3", "4", "5", "6", "7", "off", "reset"],
        description_id="opt.general.ioprio",
        comment="; By default, GameMode adjusts the iopriority of clients to BE/0"),
    OptionSpec(
        key="inhibit_screensaver", type="bool", default=True,
        description_id="opt.general.inhibit_screensaver",
        comment="; Sets whether gamemode will inhibit the screensaver when active"),
    OptionSpec(
        key="disable_splitlock", type="bool", default=True,
        description_id="opt.general.disable_splitlock",
        comment="; Sets whether gamemode will disable split lock mitigation when active"),
]
