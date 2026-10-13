"""Options of the Custom section (the ``[custom]`` keys).

The option descriptors are the single source of truth for the ``[custom]`` block.
They live here, apart from the core, so they are easy to find and edit; the core
imports them and owns the state, the rendering and the parsing.
"""

from __future__ import annotations

from typing import List

from spec import OptionSpec

CUSTOM_OPTIONS: List[OptionSpec] = [
    OptionSpec(
        key="notify_start", type="toggle_entry", default=False,
        label_id="opt.custom.notify_start.label",
        description_id="opt.custom.notify_start",
        target="start", entry='notify-send "GameMode started"'),
    OptionSpec(
        key="notify_end", type="toggle_entry", default=False,
        label_id="opt.custom.notify_end.label",
        description_id="opt.custom.notify_end",
        target="end", entry='notify-send "GameMode ended"'),
    OptionSpec(
        key="start", type="list", default=[],
        description_id="opt.custom.start",
        comment="; Custom scripts executed (via /bin/sh) when GameMode starts"),
    OptionSpec(
        key="end", type="list", default=[],
        description_id="opt.custom.end",
        comment="; Custom scripts executed (via /bin/sh) when GameMode ends"),
    OptionSpec(
        key="script_timeout", type="int", default=10, min_value=0,
        description_id="opt.custom.script_timeout",
        comment="; Timeout for scripts (seconds). Scripts are killed if they do "
                "not complete in time."),
]
