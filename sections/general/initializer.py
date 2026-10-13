"""Initializer of the General section.

Reads the ``[general]`` keys from the installed base and the ``/etc`` override
(and, only when neither exists, from the saved session) and puts them into the
section state. The shared loading logic lives in :mod:`sections.initializer`.
"""

from __future__ import annotations

from typing import Dict, Optional

from sections.general.core import GeneralCore
from sections.initializer import load_section


def initialize(core: GeneralCore, base_text: str, override_text: str,
               session_values: Optional[Dict[str, object]] = None) -> None:
    """Load the General state from the configuration texts / session."""
    load_section(core, base_text, override_text, session_values)
