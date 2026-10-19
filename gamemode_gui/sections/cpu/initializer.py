"""Initializer of the CPU section.

Reads the ``[cpu]`` keys from the installed base and the ``/etc`` override (and,
only when neither exists, from the saved session) and puts them into the state.
The shared loading logic lives in :mod:`sections.initializer`.
"""

from __future__ import annotations

from typing import Dict, Optional

from gamemode_gui.sections.cpu.core import CpuCore
from gamemode_gui.sections.initializer import load_section


def initialize(core: CpuCore, base_text: str, override_text: str,
               session_values: Optional[Dict[str, object]] = None) -> None:
    """Load the CPU state from the configuration texts / session."""
    load_section(core, base_text, override_text, session_values)
