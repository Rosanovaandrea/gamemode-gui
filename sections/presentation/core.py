"""Core of the Presentation section (stateless).

Loads the data-driven content of the Presentation tab from
``data/presentation.json``: which blocks are shown, in what order, and which are
warnings. The texts themselves live in the language files, so adding or editing
content needs no code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Tuple

# The presentation content belongs to this section and lives next to it.
_PRESENTATION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "presentation.json")


@dataclass(frozen=True)
class PresentationBlock:
    """One block of the presentation: heading + body (+ optional warning)."""

    id: str
    heading_id: str
    body_id: str
    warning: bool = False


@dataclass(frozen=True)
class Presentation:
    """Content of the Presentation tab (title, subtitle and blocks)."""

    title_id: str
    subtitle_id: str
    blocks: Tuple[PresentationBlock, ...]


def load_presentation(path: str = _PRESENTATION_FILE) -> Presentation:
    """Load the Presentation blocks from ``presentation.json``.

    A missing or broken file yields an empty presentation instead of an error.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return Presentation("presentation.title", "presentation.subtitle", ())
    blocks = tuple(
        PresentationBlock(
            id=str(block.get("id", "")),
            heading_id=block.get("heading_id", ""),
            body_id=block.get("body_id", ""),
            warning=bool(block.get("warning", False)),
        )
        for block in data.get("blocks", [])
    )
    return Presentation(
        title_id=data.get("title_id", "presentation.title"),
        subtitle_id=data.get("subtitle_id", "presentation.subtitle"),
        blocks=blocks,
    )


PRESENTATION = load_presentation()
