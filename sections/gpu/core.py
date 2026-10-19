"""Core of the GPU section."""

from __future__ import annotations

from sections.core import SectionCore
from sections.gpu.options import GPU_OPTIONS

SECTION_ID = "gpu"


class GpuCore(SectionCore):
    """State and logic of the ``[gpu]`` section."""

    section_id = SECTION_ID
    options = GPU_OPTIONS
    gate_dependencies = True
